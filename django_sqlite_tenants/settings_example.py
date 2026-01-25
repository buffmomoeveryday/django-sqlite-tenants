# The URLconf for the landing page / registration (Shared Apps)
# from core.settings import INSTALLED_APPS

ROOT_URLCONF = "django_sqlite.urls_public"
TENANT_URLCONF = "myproject.urls_tenant"
# Routing mode: 'DOMAIN', 'SUBDOMAIN', or 'SUBFOLDER'
TENANT_ROUTING_MODE = "SUBFOLDER"


# _TENANT_APPS = []
# _SHARED_APPS = []
# _INSTALLED_APPS = []
#
# _INSTALLED_APPS += [apps for apps in TENANT_APPS if apps not in SHARED_APPS]
