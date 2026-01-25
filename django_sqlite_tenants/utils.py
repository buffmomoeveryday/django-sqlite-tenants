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
