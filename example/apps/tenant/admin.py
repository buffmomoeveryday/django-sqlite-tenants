from apps.tenant.models import CustomTenant, Domain
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

from django_sqlite_tenants.admin_sites import public_admin_site

# Register your models here.
public_admin_site.register(CustomTenant)
public_admin_site.register(User, UserAdmin)
public_admin_site.register(Group, GroupAdmin)
public_admin_site.register(Domain)
