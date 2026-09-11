from django.http import HttpResponse
from django.urls import path

from django_sqlite_tenants.admin_sites import public_admin_site

urlpatterns = [
    path("", lambda request: HttpResponse("public"), name="public"),
    path("admin/", public_admin_site.urls),
]
