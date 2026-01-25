import shutil
import os
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.conf import settings
from django.db import connections
from django_sqlite_tenants.models import TenantMixin


class Command(BaseCommand):
    help = "Migrates all tenant databases with file-level rollback protection and maintenance mode."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", type=str, help="Slug of a specific tenant to migrate (optional)"
        )

    def handle(self, *args, **options):
        target_tenant = options["tenant"]

        # 1. Get Tenants
        if target_tenant:
            tenants = TenantMixin.objects.filter(slug=target_tenant)
            if not tenants.exists():
                raise CommandError(f"Tenant '{target_tenant}' not found.")
        else:
            tenants = TenantMixin.objects.all()

        self.stdout.write(f"Found {tenants.count()} tenant(s) to migrate.")

        # 2. Iterate and Migrate
        for tenant in tenants:
            self.migrate_tenant_safely(tenant)

    def migrate_tenant_safely(self, tenant):
        """
        Handles the maintenance mode, backup, migration, and rollback logic for a single tenant.
        """
        slug = tenant.slug
        # Ensure the 'tenants' directory exists
        tenant_dir = os.path.join(settings.BASE_DIR, "tenants")
        os.makedirs(tenant_dir, exist_ok=True)

        db_path = os.path.join(tenant_dir, f"{slug}.sqlite3")
        backup_path = f"{db_path}.bak"

        # Dynamically register the database connection
        settings.DATABASES[slug] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path,
            "TIME_ZONE": settings.TIME_ZONE,  # Required: prevents KeyError
            "ATOMIC_REQUESTS": False,  # Required: prevents KeyError
            "AUTOCOMMIT": True,  # Recommended default
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "OPTIONS": {
                "transaction_mode": "IMMEDIATE",
                "timeout": 5,  # seconds
                "init_command": """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA mmap_size=134217728;
                PRAGMA journal_size_limit=27103364;
                PRAGMA cache_size=2000;
            """,
            },
        }

        self.stdout.write(f"--- Processing {slug} ---")

        # 1. Enable Maintenance Mode
        # This prevents users from hitting the DB while we move files around
        self.stdout.write(f"Enabling maintenance mode for {slug}...")
        tenant.maintenance_mode = True
        tenant.save()

        try:
            # CASE A: New Tenant (File doesn't exist yet)
            if not os.path.exists(db_path):
                self.stdout.write(
                    self.style.WARNING(
                        f"Database for {slug} not found. Creating new..."
                    )
                )
                call_command("migrate", database=slug, interactive=False)
                self.stdout.write(self.style.SUCCESS(f"Created and migrated {slug}"))

            # CASE B: Existing Tenant (Requires Backup)
            else:
                # 2. Force Close Connections
                # Vital for SQLite: Release file locks before copying
                if slug in connections:
                    connections[slug].close()

                # 3. Create Backup
                shutil.copy2(db_path, backup_path)
                self.stdout.write(f"Backup created at {backup_path}")

                # 4. Run Migration
                call_command("migrate", database=slug, interactive=False)

                # 5. Clean up Backup (Success path)
                if os.path.exists(backup_path):
                    os.remove(backup_path)

                self.stdout.write(self.style.SUCCESS(f"Successfully migrated {slug}"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"ERROR migrating {slug}: {e}"))
            self.stderr.write(self.style.WARNING("Attempting rollback..."))

            # --- THE ROLLBACK PROCEDURE ---
            try:
                # A. Force close connections again (migration failure might have left it open)
                if slug in connections:
                    connections[slug].close()

                if os.path.exists(backup_path):
                    if os.path.exists(db_path):
                        os.remove(db_path)  # Remove corrupted file

                    shutil.move(backup_path, db_path)  # Restore backup
                    self.stdout.write(
                        self.style.SUCCESS("Rollback successful. Database restored.")
                    )
                else:
                    self.stderr.write(
                        self.style.ERROR(
                            "Backup missing or new file creation failed. Cannot rollback."
                        )
                    )

            except Exception as rollback_error:
                self.stderr.write(
                    self.style.ERROR(f"CRITICAL: Rollback failed! {rollback_error}")
                )

        finally:
            self.stdout.write(f"Disabling maintenance mode for {slug}...")
            tenant.refresh_from_db()
            tenant.maintenance_mode = False
            tenant.save()
