# django_sqlite_tenants/utils.py
import threading

from django.apps import apps
from .conf import conf
from django.core.exceptions import ImproperlyConfigured

_thread_locals = threading.local()


def set_current_tenant(tenant_slug):
    setattr(_thread_locals, "tenant_slug", tenant_slug)


def get_current_tenant_slug():
    return getattr(_thread_locals, "tenant_slug", None)


def get_current_tenant():
    slug = get_current_tenant_slug()
    if not slug:
        return None
    TenantModel = get_tenant_model()
    return TenantModel.objects.filter(slug=slug).first()


def get_tenant_model():
    """
    Returns the Tenant model class from the settings.
    Example setting: TENANT_MODEL = 'core.Tenant'
    """
    model_path = conf.TENANT_MODEL
    if not model_path:
        raise ImproperlyConfigured("TENANT_MODEL setting is missing.")

    try:
        return apps.get_model(model_path, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured(
            "TENANT_MODEL must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            f"TENANT_MODEL '{model_path}' has not been installed"
        )


def get_domain_model():
    """
    Returns the Domain model class from the settings.
    Example setting: DOMAIN_MODEL = 'core.Domain'
    """
    model_path = conf.DOMAIN_MODEL
    if not model_path:
        raise ImproperlyConfigured("DOMAIN_MODEL setting is missing.")

    try:
        return apps.get_model(model_path, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured(
            "DOMAIN_MODEL must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            f"DOMAIN_MODEL '{model_path}' has not been installed"
        )


def rename_tenant_database(old_slug, new_slug):
    """
    Rename a tenant's SQLite database file when the slug changes.
    """
    import os
    from django.conf import settings
    from django_sqlite_tenants.conf import conf

    # Ensure the tenants directory exists
    tenant_dir = os.path.join(settings.BASE_DIR, conf.TENANTS_DB_FOLDER)

    old_db_path = os.path.join(tenant_dir, f"{old_slug}.sqlite3")
    new_db_path = os.path.join(tenant_dir, f"{new_slug}.sqlite3")

    if os.path.exists(old_db_path):
        if os.path.exists(new_db_path):
            raise FileExistsError(f"Database file for slug '{new_slug}' already exists")
        os.rename(old_db_path, new_db_path)
