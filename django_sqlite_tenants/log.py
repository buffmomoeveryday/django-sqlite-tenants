from django_sqlite_tenants.utils import get_current_tenant
import logging


class TenantContextFilter(logging.Filter):
    """
    Add the current ``tenant_slug`` and ``domain`` to log records.
    """

    def filter(self, record):
        tenant = get_current_tenant()
        record.tenant_slug = tenant.slug if tenant else None
        record.schema_name = record.tenant_slug  # Backward compatibility
        record.domain = (
            tenant.get_primary_domain().domain
            if tenant and tenant.get_primary_domain()
            else None
        )
        return True
