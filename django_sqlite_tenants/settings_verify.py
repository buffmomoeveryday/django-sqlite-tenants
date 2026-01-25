from .settings_example import *

# Override for testing subfolder support
TENANT_ROUTING_MODE = "SUBFOLDER"
TENANT_SUBFOLDER_PREFIX = "clients"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# Mock Databases to avoid errors if not configured in verify settings
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
    }
}
SECRET_KEY = "verify"
