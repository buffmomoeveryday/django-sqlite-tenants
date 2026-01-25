from django_sqlite_tenants.admin_sites import tenant_admin_site
from apps.blog.models import Blog


tenant_admin_site.register(Blog)
