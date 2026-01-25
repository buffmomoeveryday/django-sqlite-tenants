from django.apps import AppConfig
from django.db.models.signals import post_save
from django_sqlite_tenants.utils import get_tenant_model
from django_sqlite_tenants.signals import auto_run_migrations_on_tenant_creation


class DjangoSqliteTenantsConfig(AppConfig):
    name = "django_sqlite_tenants"

    def ready(self):
        # Dynamically connect signal to the actual tenant model
        TenantModel = get_tenant_model()
        post_save.connect(auto_run_migrations_on_tenant_creation, sender=TenantModel)
