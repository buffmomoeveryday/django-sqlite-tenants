from django_sqlite_tenants.models import TenantMixin
from .conf import conf
from django.conf import settings
from django.http import HttpResponse, HttpRequest, Http404
from django.urls import set_urlconf, clear_url_caches, set_script_prefix
from .utils import set_current_tenant, get_tenant_model


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if hasattr(request, "tenant"):
            return

        # 1. Reset state for a fresh request
        set_current_tenant(None)
        set_urlconf(None)
        set_script_prefix("/")  # Ensure we start with a clean root prefix

        tenant = self.determine_tenant(request)

        if tenant:
            if tenant.maintenance_mode:
                return HttpResponse("<h1>System Under Maintenance</h1>", status=503)

            # Set Context & DB
            request.tenant = tenant  # type:ignore
            set_current_tenant(tenant.slug)
            self.register_database(tenant)

            # Switch URLConf
            tenant_urlconf = conf.TENANT_URLCONF
            if tenant_urlconf:
                request.urlconf = tenant_urlconf  # type:ignore
                set_urlconf(tenant_urlconf)
                clear_url_caches()

            # Fix Routing and URL Generation
            self._adjust_routing_for_tenant(request, tenant)
        else:
            root_urlconf = getattr(settings, "ROOT_URLCONF", None)
            if root_urlconf:
                request.urlconf = root_urlconf  # type:ignore
                set_urlconf(root_urlconf)
                clear_url_caches()

        response = self.get_response(request)

        # 2. Cleanup for the next request in this thread
        set_script_prefix("/")
        set_current_tenant(None)
        return response

    def determine_tenant(self, request: HttpRequest) -> TenantMixin | None:
        routing_mode = conf.TENANT_ROUTING_MODE
        TenantModel = get_tenant_model()

        from .enums import TenantRoutingMode

        match routing_mode:
            case TenantRoutingMode.SUBFOLDER:
                return self._resolve_by_subfolder(request, TenantModel)
            case TenantRoutingMode.DOMAIN:
                return self._resolve_by_domain(request, TenantModel)
            case _:
                return None

    def _resolve_by_domain(
        self, request: HttpRequest, TenantModel
    ) -> TenantMixin | None:
        host = request.get_host().split(":")[0]
        # Base domain should also have port stripped for matching
        base_domain = conf.TENANT_BASE_DOMAIN.split(":")[0]

        # 1. Exact Custom Domain (from Domain model)
        from django_sqlite_tenants.utils import get_domain_model

        DomainModel = get_domain_model()
        if domain_obj := DomainModel.objects.filter(
            domain=host, is_active=True
        ).first():
            return domain_obj.tenant

        # 2. Strict Subdomain (e.g. apple.localhost)
        if base_domain and host.endswith(f".{base_domain}") and host != base_domain:
            slug = host[: -(len(base_domain) + 1)]
            if tenant := TenantModel.objects.filter(slug=slug).first():
                return tenant

            raise Http404(f"Tenant '{slug}' not found.")

        return None

    def _resolve_by_subfolder(
        self, request: HttpRequest, TenantModel
    ) -> TenantMixin | None:
        path = request.path_info.strip("/")
        parts = path.split("/")
        prefix = conf.TENANT_SUBFOLDER_PREFIX.strip("/")

        slug = None
        if prefix:
            if len(parts) >= 2 and parts[0] == prefix:
                slug = parts[1]
        elif len(parts) >= 1:
            slug = parts[0]

        if slug:
            if tenant := TenantModel.objects.filter(slug=slug).first():
                return tenant

            raise Http404(f"No tenant with slug '{slug}'")

        return None

    def _adjust_routing_for_tenant(self, request: HttpRequest, tenant: TenantMixin):
        """
        Handles PATH_INFO and SCRIPT_NAME rewriting.
        Crucially uses set_script_prefix to fix {% url %} generation.
        """
        if conf.TENANT_ROUTING_MODE != "SUBFOLDER":
            return

        prefix = conf.TENANT_SUBFOLDER_PREFIX.strip("/")
        tenant_path_part = f"/{prefix}/{tenant.slug}" if prefix else f"/{tenant.slug}"

        if request.path_info.startswith(tenant_path_part):
            # 1. Update SCRIPT_NAME for the WSGI environment
            request.META["SCRIPT_NAME"] = (
                request.META.get("SCRIPT_NAME", "").rstrip("/") + tenant_path_part
            )

            # 2. Update Global Script Prefix for Template Tags ({% url %})
            set_script_prefix(tenant_path_part)

            # 3. Update PATH_INFO so the URL resolver only sees the remaining path
            new_path = request.path_info[len(tenant_path_part) :]
            request.path_info = new_path if new_path.startswith("/") else "/" + new_path

    def register_database(self, tenant: TenantMixin) -> None:
        slug = tenant.slug
        if slug not in settings.DATABASES:
            settings.DATABASES[slug] = {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": settings.BASE_DIR / conf.TENANTS_DB_FOLDER / f"{slug}.sqlite3",
                "TIME_ZONE": settings.TIME_ZONE,
                "ATOMIC_REQUESTS": False,
                "AUTOCOMMIT": True,
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": False,
                "OPTIONS": {
                    "timeout": 20,
                    "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                },
            }
