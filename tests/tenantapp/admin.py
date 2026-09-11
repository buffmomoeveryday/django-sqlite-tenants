from django_sqlite_tenants.admin_sites import tenant_admin_site

from .models import Item

tenant_admin_site.register(Item)
