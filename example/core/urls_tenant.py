# core/urls_tenant.py
from apps.blog.views import BlogCreateView, BlogDetail, BlogEditView, BlogListView
from django.urls import include, path

from django_sqlite_tenants.admin_sites import tenant_admin_site

urlpatterns = [
    path("", BlogListView.as_view(), name="blog_list_view"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("create", BlogCreateView.as_view(), name="blog_create"),
    path("detail/<int:pk>", BlogDetail.as_view(), name="blog_detail"),
    path("edit/<int:pk>", BlogEditView.as_view(), name="blog_edit"),
    path("admin/", tenant_admin_site.urls),
]
