from django.contrib import admin


class TenantAdminSite(admin.AdminSite):
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Tenant Management"


class PublicAdminSite(admin.AdminSite):
    site_header = "Public Administration"
    site_title = "Public Admin"
    index_title = "Global Management"


tenant_admin_site = TenantAdminSite(name="tenant_admin")
public_admin_site = PublicAdminSite(name="public_admin")
