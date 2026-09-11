from django_sqlite_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    pass


class Domain(DomainMixin):
    pass
