from .utils import get_current_tenant_slug


def tenant_context(request):
    return {
        "current_tenant_slug": get_current_tenant_slug(),
    }
