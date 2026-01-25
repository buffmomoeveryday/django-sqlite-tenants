from django.contrib import admin
from django_sqlite_tenants.admin_sites import tenant_admin_site
from .models import TenantUser


@admin.register(TenantUser, site=tenant_admin_site)
class TenantUserAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "is_active", "created_at")
    search_fields = ("name", "email")
