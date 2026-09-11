from typing import Any

from django.apps import AppConfig
from django.core import checks
from django.core.exceptions import ImproperlyConfigured

from .conf import conf


class DjangoSqliteTenantsConfig(AppConfig):
    name = "django_sqlite_tenants"

    def ready(self) -> None:
        checks.register(check_tenant_settings)


def check_tenant_settings(
    app_configs: Any = None, **kwargs: Any
) -> list[checks.CheckMessage]:
    from .db_routers import _app_labels
    from .enums import TenantRoutingMode
    from .models import DomainMixin, TenantMixin
    from .provisioning import get_tenant_database_directory
    from .utils import get_domain_model, get_tenant_model

    messages: list[checks.CheckMessage] = []
    if conf.AUTO_RUN_MIGRATION:
        messages.append(
            checks.Warning(
                "AUTO_RUN_MIGRATION no longer triggers tenant provisioning.",
                hint="Use create_tenant or django_sqlite_tenants.provisioning.create_tenant().",
                id="django_sqlite_tenants.W001",
            )
        )

    try:
        tenant_model = get_tenant_model()
        if not issubclass(tenant_model, TenantMixin):
            messages.append(
                checks.Error(
                    "TENANT_MODEL must inherit from TenantMixin.",
                    id="django_sqlite_tenants.E001",
                )
            )
    except ImproperlyConfigured as exc:
        messages.append(checks.Error(str(exc), id="django_sqlite_tenants.E001"))

    if conf.DOMAIN_MODEL:
        try:
            domain_model = get_domain_model()
            if not issubclass(domain_model, DomainMixin):
                messages.append(
                    checks.Error(
                        "DOMAIN_MODEL must inherit from DomainMixin.",
                        id="django_sqlite_tenants.E002",
                    )
                )
        except ImproperlyConfigured as exc:
            messages.append(checks.Error(str(exc), id="django_sqlite_tenants.E002"))

    valid_modes = {mode.value for mode in TenantRoutingMode}
    if conf.TENANT_ROUTING_MODE not in valid_modes:
        messages.append(
            checks.Error(
                f"TENANT_ROUTING_MODE must be one of {sorted(valid_modes)}.",
                id="django_sqlite_tenants.E003",
            )
        )

    overlap = _app_labels(conf.SHARED_APPS) & _app_labels(conf.TENANT_APPS)
    if overlap:
        messages.append(
            checks.Error(
                f"Apps cannot be both shared and tenant-specific: {sorted(overlap)}.",
                id="django_sqlite_tenants.E004",
            )
        )

    try:
        get_tenant_database_directory()
    except ImproperlyConfigured as exc:
        messages.append(checks.Error(str(exc), id="django_sqlite_tenants.E005"))
    return messages
