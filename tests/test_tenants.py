import asyncio
import sqlite3
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from asgiref.sync import markcoroutinefunction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404, HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings
from django.urls import get_script_prefix, get_urlconf

from django_sqlite_tenants.admin_sites import public_admin_site, tenant_admin_site
from django_sqlite_tenants.apps import check_tenant_settings
from django_sqlite_tenants.db_routers import TenantContextError, TenantRouter
from django_sqlite_tenants.management.commands.migrate_tenant import (
    Command as MigrateTenantCommand,
)
from django_sqlite_tenants.management.commands.migrate_tenant import (
    backup_sqlite_database,
)
from django_sqlite_tenants.middlewares import TenantMiddleware
from django_sqlite_tenants.provisioning import (
    create_tenant,
    get_tenant_database_path,
    normalize_domain,
    register_tenant_database,
    remove_tenant_database_files,
    tenant_lifecycle_lock,
    unregister_tenant_database,
    validate_tenant_slug,
)
from django_sqlite_tenants.utils import (
    get_current_tenant_slug,
    reset_current_tenant,
    set_current_tenant,
    tenant_context,
)
from tests.sharedapp.models import Domain, Tenant
from tests.tenantapp.models import Item


class ValidationTests(SimpleTestCase):
    def test_slug_validation(self):
        self.assertEqual(validate_tenant_slug("acme-1"), "acme-1")
        for slug in ("default", "Upper", "under_score", "-start", "end-", "../x"):
            with self.subTest(slug=slug), self.assertRaises(ValidationError):
                validate_tenant_slug(slug)

        with (
            patch.dict(
                settings.DATABASES,
                {
                    "analytics": {
                        "ENGINE": "django.db.backends.sqlite3",
                        "NAME": ":memory:",
                    }
                },
            ),
            self.assertRaises(ValidationError),
        ):
            validate_tenant_slug("analytics")

    @override_settings(
        DJANGO_TENANT_SQLITE={
            "TENANT_MODEL": "tenant_registry.Tenant",
            "DOMAIN_MODEL": "tenant_registry.Domain",
            "TENANTS_DB_FOLDER": "../escape",
        }
    )
    def test_database_folder_cannot_escape_base_dir(self):
        with self.assertRaises(ImproperlyConfigured):
            get_tenant_database_path("acme")

    def test_domain_normalization(self):
        self.assertEqual(normalize_domain("BÜCHER.Example."), "xn--bcher-kva.example")
        with self.assertRaises(ValidationError):
            normalize_domain("https://example.com/path")

    def test_context_is_task_local(self):
        async def worker(slug):
            token = set_current_tenant(slug)
            try:
                await asyncio.sleep(0)
                return get_current_tenant_slug()
            finally:
                reset_current_tenant(token)

        async def run_workers():
            return await asyncio.gather(worker("one"), worker("two"))

        self.assertEqual(asyncio.run(run_workers()), ["one", "two"])
        self.assertIsNone(get_current_tenant_slug())

    def test_lifecycle_lock_serializes_another_process(self):
        script = """
import sys
from django.conf import settings
settings.configure(
    BASE_DIR=sys.argv[1],
    SECRET_KEY="lock-test",
    INSTALLED_APPS=["django_sqlite_tenants"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    DJANGO_TENANT_SQLITE={
        "TENANT_MODEL": "placeholder.Tenant",
        "TENANTS_DB_FOLDER": "tenants",
    },
)
import django
django.setup()
from django_sqlite_tenants.provisioning import tenant_lifecycle_lock
print("ready", flush=True)
with tenant_lifecycle_lock("lock-test"):
    print("acquired", flush=True)
"""
        with tenant_lifecycle_lock("lock-test"):
            process = subprocess.Popen(
                [sys.executable, "-c", script, str(settings.BASE_DIR)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stdout is not None
            self.assertEqual(process.stdout.readline().strip(), "ready")
            time.sleep(0.1)
            self.assertIsNone(process.poll())

        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(stdout.strip(), "acquired")

    @override_settings(
        DJANGO_TENANT_SQLITE={
            "TENANT_MODEL": "tenant_registry.Tenant",
            "DOMAIN_MODEL": "tenant_registry.Domain",
            "TENANT_ROUTING_MODE": "SUBFOLDER",
            "TENANTS_DB_FOLDER": "tenants",
            "AUTO_RUN_MIGRATION": True,
        },
    )
    def test_deprecated_auto_migration_setting_warns(self):
        messages = check_tenant_settings()
        self.assertIn("django_sqlite_tenants.W001", {item.id for item in messages})


class ModelAndRouterTests(TransactionTestCase):
    reset_sequences = True

    def tearDown(self):
        set_current_tenant(None)
        for slug in ("acme", "other"):
            unregister_tenant_database(slug)
            remove_tenant_database_files(
                get_tenant_database_path(slug), include_backup=True
            )
        super().tearDown()

    def test_tenant_slug_is_immutable(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        tenant.slug = "other"
        with self.assertRaises(ValidationError) as clean_error:
            tenant.full_clean()
        self.assertIn("slug", clean_error.exception.message_dict)
        with self.assertRaisesMessage(ValidationError, "immutable"):
            tenant.save()

    def test_primary_domain_is_normalized_and_unique(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        first = Domain.objects.create(
            tenant=tenant, domain="ONE.Example.", is_primary=True
        )
        second = Domain.objects.create(
            tenant=tenant, domain="two.example", is_primary=True
        )
        first.refresh_from_db()
        self.assertEqual(first.domain, "one.example")
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_router_is_explicit_and_fails_closed(self):
        router = TenantRouter()
        shared = MagicMock()
        shared._meta.app_label = "tenant_registry"
        tenant = MagicMock()
        tenant._meta.app_label = "tenant_content"
        unknown = MagicMock()
        unknown._meta.app_label = "unknown"

        self.assertEqual(router.db_for_read(shared), "default")
        self.assertIsNone(router.db_for_read(unknown))
        with self.assertRaises(TenantContextError):
            router.db_for_read(tenant)
        with tenant_context("acme", register_database=False):
            self.assertEqual(router.db_for_write(tenant), "acme")

    @override_settings(TENANT_APPS=["missing.application.Config"])
    def test_router_rejects_unresolved_configured_apps(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "INSTALLED_APPS"):
            TenantRouter().db_for_read(Item)

    def test_cross_database_relations_are_denied(self):
        router = TenantRouter()
        shared = Tenant(name="Acme", slug="acme")
        shared._state.db = "default"
        item = Item(name="item")
        item._state.db = "acme"
        self.assertFalse(router.allow_relation(shared, item))

    def test_migrations_only_use_registered_tenant_aliases(self):
        router = TenantRouter()
        self.assertTrue(router.allow_migrate("default", "tenant_registry"))
        self.assertFalse(router.allow_migrate("default", "tenant_content"))
        self.assertFalse(router.allow_migrate("analytics", "tenant_content"))

        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        register_tenant_database("acme")
        self.assertTrue(router.allow_migrate("acme", "tenant_content"))
        self.assertFalse(router.allow_migrate("acme", "tenant_registry"))


class ProvisioningTests(TransactionTestCase):
    reset_sequences = True

    def tearDown(self):
        set_current_tenant(None)
        for slug in ("acme", "broken", "existing", "orphan"):
            unregister_tenant_database(slug)
            remove_tenant_database_files(
                get_tenant_database_path(slug), include_backup=True
            )
        super().tearDown()

    def test_create_tenant_provisions_isolated_database(self):
        with patch.object(type(self), "databases", frozenset({"default", "acme"})):
            tenant = create_tenant(
                slug="acme", name="Acme", domain="ACME.Example.Test."
            )
            self.assertEqual(tenant.domains.get().domain, "acme.example.test")
            unregister_tenant_database("acme")
            with tenant_context(tenant):
                Item.objects.create(name="private")
                self.assertEqual(Item.objects.count(), 1)
        with self.assertRaises(TenantContextError):
            Item.objects.count()

    def test_provisioning_failure_removes_metadata_and_partial_files(self):
        path = get_tenant_database_path("broken")
        with (
            patch(
                "django_sqlite_tenants.provisioning.call_command",
                side_effect=RuntimeError("migration failed"),
            ),
            self.assertRaisesMessage(RuntimeError, "migration failed"),
        ):
            create_tenant(slug="broken", name="Broken")
        self.assertFalse(Tenant.objects.filter(slug="broken").exists())
        self.assertFalse(path.exists())

    def test_registration_failure_removes_reserved_database(self):
        path = get_tenant_database_path("broken")
        with (
            patch(
                "django_sqlite_tenants.provisioning.register_tenant_database",
                side_effect=RuntimeError("registration failed"),
            ),
            self.assertRaisesMessage(RuntimeError, "registration failed"),
        ):
            create_tenant(slug="broken", name="Broken")
        self.assertFalse(Tenant.objects.filter(slug="broken").exists())
        self.assertFalse(path.exists())

    def test_domain_failure_rolls_back_metadata_and_database(self):
        path = get_tenant_database_path("broken")
        with (
            patch.object(type(self), "databases", frozenset({"default", "broken"})),
            self.assertRaises(ValidationError),
        ):
            create_tenant(
                slug="broken",
                name="Broken",
                domain="https://invalid.example/path",
            )
        self.assertFalse(Tenant.objects.filter(slug="broken").exists())
        self.assertFalse(path.exists())

    def test_existing_database_is_never_adopted(self):
        path = get_tenant_database_path("existing")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        with self.assertRaises(FileExistsError):
            create_tenant(slug="existing", name="Existing")

    def test_unprovisioned_database_cannot_be_registered(self):
        with self.assertRaises(FileNotFoundError):
            register_tenant_database("orphan")

    def test_purge_requires_orphan_and_confirmation(self):
        path = get_tenant_database_path("orphan")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        with self.assertRaises(CommandError):
            call_command("purge_tenant_database", "orphan")
        call_command("purge_tenant_database", "orphan", yes=True, verbosity=0)
        self.assertFalse(path.exists())

    def test_deleting_registry_metadata_preserves_database(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        tenant.delete()
        self.assertTrue(path.exists())


class MigrationSafetyTests(TransactionTestCase):
    def tearDown(self):
        for slug in ("acme",):
            unregister_tenant_database(slug)
            remove_tenant_database_files(
                get_tenant_database_path(slug), include_backup=True
            )
        super().tearDown()

    def test_online_backup_contains_committed_wal_data(self):
        source = get_tenant_database_path("acme")
        source.parent.mkdir(parents=True, exist_ok=True)
        backup = Path(f"{source}.bak")
        with sqlite3.connect(source) as database:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute("CREATE TABLE sample (value TEXT)")
            database.execute("INSERT INTO sample VALUES ('saved')")
            database.commit()
            backup_sqlite_database(source, backup)
        with sqlite3.connect(backup) as restored:
            self.assertEqual(
                restored.execute("SELECT value FROM sample").fetchone()[0], "saved"
            )

    def test_failed_migration_preserves_backup_and_maintenance(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE original (id INTEGER)")

        command = MigrateTenantCommand()
        with (
            patch(
                "django_sqlite_tenants.management.commands.migrate_tenant.call_command",
                side_effect=RuntimeError("bad migration"),
            ),
            self.assertRaisesMessage(RuntimeError, "bad migration"),
        ):
            command.migrate_tenant_safely(tenant)

        tenant.refresh_from_db()
        self.assertTrue(tenant.maintenance_mode)
        self.assertTrue(Path(f"{path}.bak").exists())

    def test_failed_first_migration_removes_partial_database(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        command = MigrateTenantCommand()
        with (
            patch(
                "django_sqlite_tenants.management.commands.migrate_tenant.call_command",
                side_effect=RuntimeError("bad migration"),
            ),
            self.assertRaisesMessage(RuntimeError, "bad migration"),
        ):
            command.migrate_tenant_safely(tenant)
        tenant.refresh_from_db()
        self.assertTrue(tenant.maintenance_mode)
        self.assertFalse(path.exists())

    def test_failed_reservation_does_not_remove_preexisting_sidecar(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        sidecar = Path(f"{path}-wal")
        sidecar.write_bytes(b"preexisting")

        with self.assertRaises(FileExistsError):
            MigrateTenantCommand().migrate_tenant_safely(tenant)

        tenant.refresh_from_db()
        self.assertTrue(tenant.maintenance_mode)
        self.assertEqual(sidecar.read_bytes(), b"preexisting")

    def test_successful_migration_removes_backup_and_maintenance(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme", maintenance_mode=True)
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE original (id INTEGER)")

        with patch(
            "django_sqlite_tenants.management.commands.migrate_tenant.call_command"
        ):
            MigrateTenantCommand().migrate_tenant_safely(tenant)

        tenant.refresh_from_db()
        self.assertFalse(tenant.maintenance_mode)
        self.assertFalse(Path(f"{path}.bak").exists())

    def test_maintenance_save_failure_preserves_backup(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE original (id INTEGER)")

        original_save = tenant.save

        def save_or_fail(*args, **kwargs):
            if not tenant.maintenance_mode:
                raise RuntimeError("shared save failed")
            return original_save(*args, **kwargs)

        with (
            patch(
                "django_sqlite_tenants.management.commands.migrate_tenant.call_command"
            ),
            patch.object(tenant, "save", side_effect=save_or_fail),
            self.assertRaisesMessage(RuntimeError, "shared save failed"),
        ):
            MigrateTenantCommand().migrate_tenant_safely(tenant)

        tenant.refresh_from_db()
        self.assertTrue(tenant.maintenance_mode)
        self.assertTrue(Path(f"{path}.bak").exists())

    def test_backup_cleanup_failure_is_only_a_warning(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        backup_path = Path(f"{path}.bak")
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE original (id INTEGER)")

        original_unlink = Path.unlink

        def fail_backup_cleanup(candidate, *args, **kwargs):
            if candidate == backup_path:
                raise PermissionError("read-only backup")
            return original_unlink(candidate, *args, **kwargs)

        stderr = StringIO()
        with (
            patch(
                "django_sqlite_tenants.management.commands.migrate_tenant.call_command"
            ),
            patch.object(Path, "unlink", fail_backup_cleanup),
        ):
            MigrateTenantCommand(stderr=stderr).migrate_tenant_safely(tenant)

        tenant.refresh_from_db()
        self.assertFalse(tenant.maintenance_mode)
        self.assertTrue(backup_path.exists())
        self.assertIn("backup cleanup failed", stderr.getvalue())

    def test_batch_migration_continues_and_reports_failure(self):
        Tenant.objects.create(name="Acme", slug="acme")
        Tenant.objects.create(name="Other", slug="other")
        command = MigrateTenantCommand()
        with (
            patch.object(
                command,
                "migrate_tenant_safely",
                side_effect=[RuntimeError("first"), None],
            ) as migrate,
            self.assertRaises(CommandError),
        ):
            command.handle(tenant=None)
        self.assertEqual(migrate.call_count, 2)


class MiddlewareTests(TransactionTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        path = get_tenant_database_path("acme")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def tearDown(self):
        set_current_tenant(None)
        unregister_tenant_database("acme")
        remove_tenant_database_files(
            get_tenant_database_path("acme"), include_backup=True
        )
        super().tearDown()

    def test_subfolder_request_and_stream_restore_context(self):
        response = Client().get("/r/acme/")
        self.assertEqual(response.content, b"acme")
        self.assertIsNone(get_current_tenant_slug())

        response = Client().get("/r/acme/stream/")
        content = iter(response.streaming_content)
        self.assertEqual(next(content), b"acme")
        self.assertIsNone(get_current_tenant_slug())
        self.assertEqual(next(content), b"acme")
        self.assertIsNone(get_current_tenant_slug())

    @override_settings(
        DJANGO_TENANT_SQLITE={
            "TENANT_MODEL": "tenant_registry.Tenant",
            "DOMAIN_MODEL": "tenant_registry.Domain",
            "TENANT_URLCONF": "tests.urls_tenant",
            "TENANT_ROUTING_MODE": "SUBFOLDER",
            "TENANT_SUBFOLDER_PREFIX": "",
            "TENANT_BASE_DOMAIN": "example.test",
            "TENANTS_DB_FOLDER": "tenants",
        }
    )
    def test_empty_subfolder_prefix_does_not_capture_public_paths(self):
        request = self.factory.get("/acme/")
        middleware = TenantMiddleware(lambda request: HttpResponse("public"))
        self.assertIsNone(middleware.determine_tenant(request))

    def test_marked_async_response_uses_async_path(self):
        class MarkedResponse:
            async def __call__(self, request):
                return HttpResponse()

        response = MarkedResponse()
        markcoroutinefunction(response)
        self.assertTrue(TenantMiddleware(response).is_async)

    def test_existing_request_tenant_continues_and_exception_restores_state(self):
        request = self.factory.get("/")
        request.tenant = self.tenant
        old_urlconf = get_urlconf()
        old_prefix = get_script_prefix()

        def explode(request):
            self.assertEqual(get_current_tenant_slug(), "acme")
            raise RuntimeError("boom")

        middleware = TenantMiddleware(explode)
        with self.assertRaisesMessage(RuntimeError, "boom"):
            middleware(request)
        self.assertIsNone(get_current_tenant_slug())
        self.assertEqual(get_urlconf(), old_urlconf)
        self.assertEqual(get_script_prefix(), old_prefix)

    async def test_async_middleware_uses_task_local_context(self):
        request = self.factory.get("/")
        request.tenant = self.tenant

        async def response(request):
            await asyncio.sleep(0)
            return HttpResponse(get_current_tenant_slug())

        result = await TenantMiddleware(response)(request)
        self.assertEqual(result.content, b"acme")
        self.assertIsNone(get_current_tenant_slug())

    async def test_async_stream_retains_tenant_context(self):
        request = self.factory.get("/")
        request.tenant = self.tenant

        async def content():
            await asyncio.sleep(0)
            yield get_current_tenant_slug() or "missing"
            await asyncio.sleep(0)
            yield get_current_tenant_slug() or "missing"

        async def response(request):
            from django.http import StreamingHttpResponse

            return StreamingHttpResponse(content())

        wrapped = await TenantMiddleware(response)(request)
        content_iterator = wrapped.streaming_content.__aiter__()
        self.assertEqual(await anext(content_iterator), b"acme")
        self.assertIsNone(get_current_tenant_slug())
        self.assertEqual(await anext(content_iterator), b"acme")
        self.assertIsNone(get_current_tenant_slug())

    def test_admin_sites_render_stock_templates(self):
        client = Client()
        self.assertEqual(client.get("/admin/login/").status_code, 200)
        self.assertEqual(client.get("/r/acme/admin/login/").status_code, 200)
        self.assertIn(Tenant, public_admin_site._registry)
        self.assertNotIn(Item, public_admin_site._registry)
        self.assertIn(Item, tenant_admin_site._registry)

        user = get_user_model().objects.create_superuser(
            username="admin", password="password"
        )
        client.force_login(user)
        self.assertEqual(client.get("/admin/").status_code, 200)
        self.assertEqual(client.get("/r/acme/admin/").status_code, 200)

        request = self.factory.get("/")
        request.user = user
        self.assertEqual(
            public_admin_site._registry[Tenant].get_queryset(request).db, "default"
        )
        with tenant_context(self.tenant):
            self.assertEqual(
                tenant_admin_site._registry[Item].get_queryset(request).db, "acme"
            )

    def test_maintenance_mode_short_circuits_request(self):
        self.tenant.maintenance_mode = True
        self.tenant.save(update_fields=["maintenance_mode"])
        self.assertEqual(Client().get("/r/acme/").status_code, 503)

    @override_settings(
        ALLOWED_HOSTS=["custom.example", ".example.test"],
        DJANGO_TENANT_SQLITE={
            "TENANT_MODEL": "tenant_registry.Tenant",
            "DOMAIN_MODEL": "tenant_registry.Domain",
            "TENANT_URLCONF": "tests.urls_tenant",
            "TENANT_ROUTING_MODE": "DOMAIN",
            "TENANT_BASE_DOMAIN": "example.test:443",
            "TENANTS_DB_FOLDER": "tenants",
        },
    )
    def test_domain_and_subdomain_resolution(self):
        Domain.objects.create(
            tenant=self.tenant, domain="custom.example", is_primary=True
        )
        middleware = TenantMiddleware(lambda request: HttpResponse())
        custom = self.factory.get("/", HTTP_HOST="CUSTOM.EXAMPLE:443")
        self.assertEqual(middleware.determine_tenant(custom), self.tenant)
        subdomain = self.factory.get("/", HTTP_HOST="acme.example.test:443")
        self.assertEqual(middleware.determine_tenant(subdomain), self.tenant)
        missing = self.factory.get("/", HTTP_HOST="missing.example.test")
        with self.assertRaises(Http404):
            middleware.determine_tenant(missing)
