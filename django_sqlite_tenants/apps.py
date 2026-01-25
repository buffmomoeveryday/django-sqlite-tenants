from django.apps import AppConfig


class DjangoSqliteTenantsConfig(AppConfig):
    name = "django_sqlite_tenants"

    def ready(self):
        # Import signals to connect them
        import django_sqlite_tenants.signals  # noqa: F401
