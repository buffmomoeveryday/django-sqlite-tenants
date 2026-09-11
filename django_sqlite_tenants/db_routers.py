from collections.abc import Iterable
from typing import Any

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from .conf import conf
from .provisioning import is_tenant_database_alias
from .utils import get_current_tenant_slug


class TenantContextError(ImproperlyConfigured):
    """Raised when tenant data is accessed without an active tenant."""


def _app_labels(entries: Iterable[str]) -> set[str]:
    labels: set[str] = set()
    configs = list(apps.get_app_configs())
    for entry in entries:
        match = next(
            (
                config
                for config in configs
                if entry
                in {
                    config.label,
                    config.name,
                    f"{config.__class__.__module__}.{config.__class__.__name__}",
                }
            ),
            None,
        )
        if match is None:
            raise ImproperlyConfigured(
                f"Configured app '{entry}' is not present in INSTALLED_APPS."
            )
        labels.add(match.label)
    return labels


class TenantRouter:
    def _route(self, model: type[models.Model]) -> str | None:
        label = model._meta.app_label
        if label in _app_labels(conf.SHARED_APPS):
            return "default"
        if label in _app_labels(conf.TENANT_APPS):
            tenant_slug = get_current_tenant_slug()
            if not tenant_slug:
                raise TenantContextError(
                    f"Tenant app '{label}' was accessed without an active tenant."
                )
            return tenant_slug
        return None

    def db_for_read(self, model: type[models.Model], **hints: Any) -> str | None:
        return self._route(model)

    def db_for_write(self, model: type[models.Model], **hints: Any) -> str | None:
        return self._route(model)

    def allow_relation(
        self, obj1: models.Model, obj2: models.Model, **hints: Any
    ) -> bool | None:
        database1 = obj1._state.db
        database2 = obj2._state.db
        if database1 and database2:
            return database1 == database2

        label1 = obj1._meta.app_label
        label2 = obj2._meta.app_label
        shared = _app_labels(conf.SHARED_APPS)
        tenant = _app_labels(conf.TENANT_APPS)
        if (label1 in shared and label2 in tenant) or (
            label1 in tenant and label2 in shared
        ):
            return False
        return None

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool | None:
        shared = _app_labels(conf.SHARED_APPS)
        tenant = _app_labels(conf.TENANT_APPS)
        if db == "default":
            return app_label in shared
        if is_tenant_database_alias(db):
            return app_label in tenant
        if app_label in shared or app_label in tenant:
            return False
        return None
