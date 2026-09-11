from typing import Any

from django.conf import settings

from django_sqlite_tenants.enums import TenantRoutingMode


class AppSettings:
    def __init__(self) -> None:
        self._defaults: dict[str, Any] = {
            "TENANT_MODEL": None,
            "DOMAIN_MODEL": None,
            "TENANT_URLCONF": None,
            "TENANT_ROUTING_MODE": TenantRoutingMode.DOMAIN,
            "TENANT_SUBFOLDER_PREFIX": "r",
            "TENANT_BASE_DOMAIN": "localhost",
            "TENANTS_DB_FOLDER": "tenants",
            "SHARED_APPS": [],
            "TENANT_APPS": [],
            "AUTO_RUN_MIGRATION": False,
        }

    @property
    def user_settings(self) -> dict[str, Any]:
        return getattr(settings, "DJANGO_TENANT_SQLITE", {})

    def __getattr__(self, name: str) -> Any:
        # Special handling for TENANT_APPS and SHARED_APPS to allow them to be top-level
        if name in ["TENANT_APPS", "SHARED_APPS"]:
            if name in self.user_settings:
                return self.user_settings[name]
            if hasattr(settings, name):
                return getattr(settings, name)
            if name == "SHARED_APPS":
                tenant_apps = self.TENANT_APPS
                installed_apps = getattr(settings, "INSTALLED_APPS", [])
                return [app for app in installed_apps if app not in tenant_apps]
            return self._defaults.get(name, [])

        if name in self.user_settings:
            return self.user_settings[name]

        if hasattr(settings, name):
            return getattr(settings, name)

        if name in self._defaults:
            return self._defaults[name]

        raise AttributeError(name)


conf = AppSettings()
