import atexit
import shutil
import tempfile
from pathlib import Path

BASE_DIR = Path(tempfile.mkdtemp(prefix="django-sqlite-tenants-tests-"))
atexit.register(shutil.rmtree, BASE_DIR, ignore_errors=True)
SECRET_KEY = "tests-only-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver", ".example.test", "localhost"]
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_sqlite_tenants",
    "tests.sharedapp.apps.SharedAppConfig",
]
TENANT_APPS = ["tests.tenantapp.apps.TenantAppConfig"]
INSTALLED_APPS = SHARED_APPS + TENANT_APPS

DJANGO_TENANT_SQLITE = {
    "TENANT_MODEL": "tenant_registry.Tenant",
    "DOMAIN_MODEL": "tenant_registry.Domain",
    "TENANT_URLCONF": "tests.urls_tenant",
    "TENANT_ROUTING_MODE": "SUBFOLDER",
    "TENANT_SUBFOLDER_PREFIX": "r",
    "TENANT_BASE_DOMAIN": "example.test",
    "TENANTS_DB_FOLDER": "tenants",
    "AUTO_RUN_MIGRATION": False,
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "shared.sqlite3",
        "TEST": {"NAME": BASE_DIR / "test-shared.sqlite3"},
    }
}
DATABASE_ROUTERS = ["django_sqlite_tenants.db_routers.TenantRouter"]
ROOT_URLCONF = "tests.urls_public"
MIDDLEWARE = [
    "django_sqlite_tenants.middlewares.TenantMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
