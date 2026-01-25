from django.conf import settings


class AppSettings:
    def __init__(self):
        self._defaults = {
            "TENANT_MODEL": None,
            "DOMAIN_MODEL": None,
            "TENANT_URLCONF": None,
            "TENANT_ROUTING_MODE": "DOMAIN",
            "TENANT_SUBFOLDER_PREFIX": "r",
            "TENANT_BASE_DOMAIN": "localhost",
            "TENANTS_DB_FOLDER": "tenants",
            "SHARED_APPS": [],
            "TENANT_APPS": [],
            "AUTO_RUN_MIGRATION": True,
        }

    @property
    def user_settings(self):
        return getattr(settings, "DJANGO_TENANT_SQLITE", {})

    def __getattr__(self, name):
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
