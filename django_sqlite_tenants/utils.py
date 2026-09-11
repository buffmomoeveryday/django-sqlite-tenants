from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, TypeVar, cast

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model

from .conf import conf

if TYPE_CHECKING:
    from .models import DomainMixin, TenantMixin

_current_tenant_slug: ContextVar[str | None] = ContextVar(
    "django_sqlite_tenants_slug", default=None
)
_TenantContextValue = TypeVar("_TenantContextValue", bound=str | Model)


def set_current_tenant(tenant_slug: str | None) -> Token[str | None]:
    """Set the current tenant and return a token that can restore prior state."""
    return _current_tenant_slug.set(tenant_slug)


def reset_current_tenant(token: Token[str | None]) -> None:
    """Restore tenant state previously returned by :func:`set_current_tenant`."""
    _current_tenant_slug.reset(token)


def get_current_tenant_slug() -> str | None:
    return _current_tenant_slug.get()


@contextmanager
def tenant_context(
    tenant_or_slug: _TenantContextValue, *, register_database: bool = True
) -> Iterator[_TenantContextValue]:
    """Activate a tenant and its database for a synchronous context."""
    slug = cast(str, getattr(tenant_or_slug, "slug", tenant_or_slug))
    if register_database:
        from .provisioning import register_tenant_database

        register_tenant_database(slug)
    token = set_current_tenant(slug)
    try:
        yield tenant_or_slug
    finally:
        reset_current_tenant(token)


def get_current_tenant() -> "TenantMixin | None":
    slug = get_current_tenant_slug()
    if not slug:
        return None
    TenantModel = get_tenant_model()
    return TenantModel.objects.filter(slug=slug).first()


def get_tenant_model() -> type["TenantMixin"]:
    """
    Returns the Tenant model class from the settings.
    Example setting: TENANT_MODEL = 'core.Tenant'
    """
    model_path = conf.TENANT_MODEL
    if not model_path:
        raise ImproperlyConfigured("TENANT_MODEL setting is missing.")

    try:
        return cast(
            type["TenantMixin"], apps.get_model(model_path, require_ready=False)
        )
    except ValueError:
        raise ImproperlyConfigured(
            "TENANT_MODEL must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            f"TENANT_MODEL '{model_path}' has not been installed"
        )


def get_domain_model() -> type["DomainMixin"]:
    """
    Returns the Domain model class from the settings.
    Example setting: DOMAIN_MODEL = 'core.Domain'
    """
    model_path = conf.DOMAIN_MODEL
    if not model_path:
        raise ImproperlyConfigured("DOMAIN_MODEL setting is missing.")

    try:
        return cast(
            type["DomainMixin"], apps.get_model(model_path, require_ready=False)
        )
    except ValueError:
        raise ImproperlyConfigured(
            "DOMAIN_MODEL must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            f"DOMAIN_MODEL '{model_path}' has not been installed"
        )
