from typing import Any

from django.http import HttpRequest

from .utils import get_current_tenant_slug


def tenant_context(request: HttpRequest) -> dict[str, Any]:
    return {
        "current_tenant_slug": get_current_tenant_slug(),
    }
