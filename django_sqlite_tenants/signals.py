import os
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django_sqlite_tenants.models import TenantMixin
from django_sqlite_tenants.conf import conf


@receiver(post_save, sender=TenantMixin)
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

    # Dynamically register the database connection
    settings.DATABASES[slug] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": db_path,
        "TIME_ZONE": settings.TIME_ZONE,
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 5,
            "init_command": """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA mmap_size=134217728;
            PRAGMA journal_size_limit=27103364;
            PRAGMA cache_size=2000;
        """,
        },
    }

    try:
        # Run migrations for the new tenant
        call_command("migrate", database=slug, interactive=False)
    except Exception as e:
        # Handle any errors during migration
        logging.error(f"Error migrating tenant {slug}: {e}")
    finally:
        # Cleanup: Close the connection and remove from settings
        if slug in connections:
            connections[slug].close()
