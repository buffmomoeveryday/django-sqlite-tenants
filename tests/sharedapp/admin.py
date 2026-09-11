from django.contrib import admin

from django_sqlite_tenants.admin_sites import public_admin_site

from .models import Domain, Tenant

public_admin_site.register(Tenant)
public_admin_site.register(Domain)
public_admin_site.register(admin.models.LogEntry)
