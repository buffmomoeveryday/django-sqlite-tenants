from apps.blog.models import Blog

from django_sqlite_tenants.admin_sites import tenant_admin_site

tenant_admin_site.register(Blog)
