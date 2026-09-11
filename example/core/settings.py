import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Add the root directory to sys.path to ensure django_sqlite_tenants is importable
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-example-only-change-me-before-deployment"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in production.")

allowed_hosts_setting = os.environ.get("DJANGO_ALLOWED_HOSTS")
if not allowed_hosts_setting and not DEBUG:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required in production.")
ALLOWED_HOSTS = [
    host.strip()
    for host in (allowed_hosts_setting or "localhost,127.0.0.1,.localhost").split(",")
    if host.strip()
]


SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_sqlite_tenants",
    "apps.tenant",
]

TENANT_APPS = [
    "apps.blog",
    "apps.tenant_users",
]

INSTALLED_APPS = SHARED_APPS + TENANT_APPS

DJANGO_TENANT_SQLITE = {
    "TENANT_MODEL": "tenant.CustomTenant",
    "DOMAIN_MODEL": "tenant.Domain",
    "TENANT_URLCONF": "core.urls_tenant",
    "TENANT_ROUTING_MODE": "DOMAIN",
    "TENANT_SUBFOLDER_PREFIX": "r",
    "TENANT_BASE_DOMAIN": "localhost:8000",
    "TENANTS_DB_FOLDER": "tenants",
    "AUTO_RUN_MIGRATION": False,
}


MIDDLEWARE = [
    "django_sqlite_tenants.middlewares.TenantMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls_public"

DATABASE_ROUTERS = [
    "django_sqlite_tenants.db_routers.TenantRouter",
]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            Path(BASE_DIR / "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django_sqlite_tenants.context_processors.tenant_context",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
LOGIN_REDIRECT_URL = "/"


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 5,  # seconds
            "init_command": """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                PRAGMA mmap_size=134217728;
                PRAGMA journal_size_limit=27103364;
                PRAGMA cache_size=2000;
            """,
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "static/"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
