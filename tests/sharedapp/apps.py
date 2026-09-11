from django.apps import AppConfig


class SharedAppConfig(AppConfig):
    name = "tests.sharedapp"
    label = "tenant_registry"
