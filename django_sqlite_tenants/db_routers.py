# django_sqlite_tenants/db_routes.py
from .utils import get_current_tenant_slug
from .conf import conf

DJANGO_CACHE_APP_LABEL = "django_cache"


class TenantRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label in self._get_shared_app_labels():
            return "default"

        tenant_slug = get_current_tenant_slug()
        if tenant_slug:
            return tenant_slug
        return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self._get_shared_app_labels():
            return "default"

        tenant_slug = get_current_tenant_slug()
        if tenant_slug:
            return tenant_slug
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        # Allow if both are in the same DB or if one is in default (shared)
        db_list = (self.db_for_read(obj1), self.db_for_read(obj2))
        if db_list[0] == db_list[1]:
            return True

        # Allow relations between tenant and shared apps
        if "default" in db_list:
            return True

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        shared_labels = self._get_shared_app_labels()
        tenant_labels = [app.split(".")[-1] for app in conf.TENANT_APPS]

        if db == "default":
            # Allow shared apps and those not strictly defined as tenant apps
            # (unless generic third party apps are considered shared by default)
            return app_label in shared_labels
        else:
            return app_label in tenant_labels

    def _get_shared_app_labels(self):
        return [app.split(".")[-1] for app in conf.SHARED_APPS]
