from django.shortcuts import render
from django.http import HttpResponse
from django.urls import path, include
from django_sqlite_tenants.admin_sites import public_admin_site


def index(request):
    return render(request, "index.html")


def another_page(request):
    return HttpResponse("another page")


urlpatterns = [
    path("", index),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", public_admin_site.urls),
    path("another-page", another_page, name="another-page"),
]
