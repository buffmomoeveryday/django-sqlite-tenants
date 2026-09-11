import os
import sqlite3
from pathlib import Path
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DEFAULT_DB_ALIAS, connections

from django_sqlite_tenants.models import TenantMixin
from django_sqlite_tenants.provisioning import (
    get_tenant_database_path,
    register_tenant_database,
    remove_tenant_database_files,
    reserve_tenant_database,
    tenant_lifecycle_lock,
    unregister_tenant_database,
)
from django_sqlite_tenants.utils import get_tenant_model, tenant_context


def backup_sqlite_database(database_path: Path, backup_path: Path) -> None:
    """Create a consistent SQLite backup, including committed WAL contents."""
    try:
        descriptor = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Refusing to overwrite existing backup: {backup_path}"
        ) from exc
    os.close(descriptor)
    try:
        with sqlite3.connect(database_path, timeout=20) as source:
            with sqlite3.connect(backup_path, timeout=20) as destination:
                source.backup(destination)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


class Command(BaseCommand):
    help = "Migrate tenant databases with consistent backups and failure isolation."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--tenant", help="Slug of one tenant; defaults to all")

    def handle(self, *args: Any, **options: Any) -> None:
        TenantModel = get_tenant_model()
        tenants = TenantModel.objects.using(DEFAULT_DB_ALIAS).all()
        if options.get("tenant"):
            tenants = tenants.filter(slug=options["tenant"])
            if not tenants.exists():
                raise CommandError(f"Tenant '{options['tenant']}' not found.")

        tenants = list(tenants)
        self.stdout.write(f"Found {len(tenants)} tenant(s) to migrate.")
        failures: list[tuple[str, str]] = []
        for tenant in tenants:
            try:
                self.migrate_tenant_safely(tenant)
            except Exception as exc:
                failures.append((tenant.slug, str(exc)))
                self.stderr.write(self.style.ERROR(f"{tenant.slug}: {exc}"))

        if failures:
            summary = "; ".join(f"{slug}: {error}" for slug, error in failures)
            raise CommandError(f"{len(failures)} tenant migration(s) failed: {summary}")

    def migrate_tenant_safely(self, tenant: TenantMixin) -> None:
        with tenant_lifecycle_lock(tenant.slug):
            self._migrate_tenant_locked(tenant)

    def _migrate_tenant_locked(self, tenant: TenantMixin) -> None:
        slug = tenant.slug
        database_path = get_tenant_database_path(slug)
        backup_path = Path(f"{database_path}.bak")
        existed = database_path.exists()
        created = False
        backup_created = False

        self.stdout.write(f"--- Processing {slug} ---")
        tenant.maintenance_mode = True
        tenant.save(using=DEFAULT_DB_ALIAS, update_fields=["maintenance_mode"])
        registered = False
        try:
            if not existed:
                reserve_tenant_database(slug)
                created = True
            register_tenant_database(slug)
            registered = True
            connections[slug].close()
            if existed:
                backup_sqlite_database(database_path, backup_path)
                backup_created = True
                self.stdout.write(f"Backup created at {backup_path}")

            with tenant_context(slug):
                call_command("migrate", database=slug, interactive=False)

            connections[slug].close()
            tenant.maintenance_mode = False
            tenant.save(using=DEFAULT_DB_ALIAS, update_fields=["maintenance_mode"])
            if backup_created:
                try:
                    backup_path.unlink()
                except OSError as exc:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Migration succeeded, but backup cleanup failed; "
                            f"{backup_path} was retained: {exc}"
                        )
                    )
            self.stdout.write(self.style.SUCCESS(f"Successfully migrated {slug}"))
        except Exception:
            if registered:
                connections[slug].close()
            if backup_created:
                recovery = (
                    "Restore the preserved backup only while application workers "
                    "are stopped."
                )
            elif existed:
                recovery = (
                    "The existing database was left in place, but no usable backup "
                    "was created."
                )
            elif created:
                remove_tenant_database_files(database_path)
                recovery = "The partial new database was removed and can be retried."
            else:
                recovery = (
                    "No files were removed because the database filename could not "
                    "be reserved safely."
                )
            self.stderr.write(
                self.style.WARNING(
                    f"Migration failed; maintenance remains enabled. {recovery}"
                )
            )
            raise
        finally:
            if registered:
                unregister_tenant_database(slug)
