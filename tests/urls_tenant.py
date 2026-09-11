from django.http import HttpResponse, StreamingHttpResponse
from django.urls import path

from django_sqlite_tenants.admin_sites import tenant_admin_site
from django_sqlite_tenants.utils import get_current_tenant_slug


def current_tenant(request):
    return HttpResponse(get_current_tenant_slug() or "missing")


def stream_tenant(request):
    def content():
        yield get_current_tenant_slug() or "missing"
        yield get_current_tenant_slug() or "missing"

    return StreamingHttpResponse(content())


urlpatterns = [
    path("", current_tenant, name="tenant-home"),
    path("stream/", stream_tenant, name="tenant-stream"),
    path("admin/", tenant_admin_site.urls),
]
