from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin

from django_sqlite_tenants.admin_sites import public_admin_site, PublicAdminSite
from apps.tenant.models import CustomTenant, Domain

# Register your models here.
public_admin_site.register(CustomTenant)
public_admin_site.register(User, UserAdmin)
public_admin_site.register(Group, GroupAdmin)
public_admin_site.register(Domain)
