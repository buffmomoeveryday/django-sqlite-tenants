# django_sqlite_tenants/management/commands/create_tenant.py

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
from django.db.utils import DEFAULT_DB_ALIAS  # Import this constant
from django_sqlite_tenants.utils import get_tenant_model
import os


class Command(BaseCommand):
    help = "Creates a new tenant and initializes their database"

    def add_arguments(self, parser):
        parser.add_argument(
            "slug", type=str, help='Unique identifier for the tenant (e.g., "acme")'
        )
        parser.add_argument(
            "--name", type=str, help="Display name (defaults to slug)", required=False
        )
        parser.add_argument(
            "--domain", type=str, help="Custom domain (optional)", required=False
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        name = options.get("name") or slug.title()
        domain = options.get("domain")

        Tenant = get_tenant_model()

        # 1. Validation
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"Tenant with slug '{slug}' already exists.")

        self.stdout.write(f"Creating tenant '{name}' ({slug})...")

        # 2. Create the Tenant Record (in the shared 'default' DB)
        try:
            tenant = Tenant.objects.create(slug=slug, name=name)
            self.stdout.write(self.style.SUCCESS("Tenant record created."))

            # Create domain if provided
            if domain:
                from django_sqlite_tenants.utils import get_domain_model

                DomainModel = get_domain_model()
                DomainModel.objects.create(
                    tenant=tenant, domain=domain, is_primary=True, is_active=True
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Domain '{domain}' created and set as primary.")
                )

        except Exception as e:
            raise CommandError(f"Failed to create tenant record: {e}")

        # 3. Dynamic Database Configuration
        db_path = f"tenants/{slug}.sqlite3"

        # --- FIX STARTS HERE ---
        # Copy the 'default' config to inherit TIME_ZONE, OPTIONS, etc.
        tenant_db_config = settings.DATABASES[DEFAULT_DB_ALIAS].copy()

        # Overwrite the specific fields for this tenant
        tenant_db_config["NAME"] = db_path
        tenant_db_config["ENGINE"] = "django.db.backends.sqlite3"  # Force SQLite

        # Inject into settings
        settings.DATABASES[slug] = tenant_db_config
        # --- FIX ENDS HERE ---

        # Ensure the tenants directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 4. Run Migrations for this specific tenant
        self.stdout.write(f"Migrating database: {db_path}...")

        try:
            call_command("migrate", database=slug, verbosity=0)
            self.stdout.write(self.style.SUCCESS("Database migrated successfully."))
            self.stdout.write(
                self.style.SUCCESS(f"All Done! Tenant '{slug}' is ready.")
            )

        except Exception as e:
            # Rollback (delete the tenant) if migration fails
            self.stdout.write(self.style.ERROR(f"Migration failed: {e}"))
            self.stdout.write("Rolling back tenant record...")
            tenant.delete()
            if os.path.exists(db_path):
                os.remove(db_path)
            raise CommandError("Migration failed. Tenant rolled back.")
