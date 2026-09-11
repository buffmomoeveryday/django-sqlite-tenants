import logging
from typing import Any, cast

from django_sqlite_tenants.utils import get_current_tenant


class TenantContextFilter(logging.Filter):
    """
    Add the current ``tenant_slug`` and ``domain`` to log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        tenant = get_current_tenant()
        typed_record = cast(Any, record)
        typed_record.tenant_slug = tenant.slug if tenant else None
        typed_record.schema_name = typed_record.tenant_slug
        primary_domain = tenant.get_primary_domain() if tenant else None
        typed_record.domain = primary_domain.domain if primary_domain else None
        return True
