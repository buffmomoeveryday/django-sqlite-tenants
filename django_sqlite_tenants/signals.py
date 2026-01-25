import os
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django_sqlite_tenants.utils import get_tenant_model
from django_sqlite_tenants.conf import conf
from django.db.utils import DEFAULT_DB_ALIAS


def auto_run_migrations_on_tenant_creation(sender, instance, created, **kwargs):
    """
    Automatically runs migrations when a new tenant is created if AUTO_RUN_MIGRATION is True.
    """
    if not created:
        return

    if not conf.AUTO_RUN_MIGRATION:
        return

    slug = instance.slug

    # Ensure the 'tenants' directory exists
    tenant_dir = os.path.join(settings.BASE_DIR, conf.TENANTS_DB_FOLDER)
    os.makedirs(tenant_dir, exist_ok=True)

    db_path = os.path.join(tenant_dir, f"{slug}.sqlite3")

    # Dynamic Database Configuration - copy default config to inherit settings
    tenant_db_config = settings.DATABASES[DEFAULT_DB_ALIAS].copy()
    tenant_db_config["NAME"] = db_path
    tenant_db_config["ENGINE"] = "django.db.backends.sqlite3"  # Force SQLite

    # Inject into settings
    settings.DATABASES[slug] = tenant_db_config

    try:
        # Run migrations for the new tenant
        call_command("migrate", database=slug, interactive=False)
        logging.info(f"Successfully migrated tenant {slug}")
    except Exception as e:
        # Handle any errors during migration
        logging.error(f"Error migrating tenant {slug}: {e}")
        # Optionally, you could delete the tenant record here if migration fails
        # instance.delete()
    finally:
        # Cleanup: Close the connection and remove from settings
        if slug in connections:
            connections[slug].close()
        if slug in settings.DATABASES:
            del settings.DATABASES[slug]
