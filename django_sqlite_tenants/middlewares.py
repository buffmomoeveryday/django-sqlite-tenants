from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from inspect import iscoroutinefunction
from typing import Any, cast

from asgiref.sync import markcoroutinefunction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.urls import (
    get_script_prefix,
    get_urlconf,
    set_script_prefix,
    set_urlconf,
)

from .conf import conf
from .enums import TenantRoutingMode
from .models import TenantMixin
from .provisioning import normalize_domain, register_tenant_database
from .utils import (
    get_domain_model,
    get_tenant_model,
    reset_current_tenant,
    set_current_tenant,
)


class TenantMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[
            [HttpRequest], HttpResponseBase | Awaitable[HttpResponseBase]
        ],
    ) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(cast(Any, self))

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.is_async:
            return self.__acall__(request)
        return self._call_sync(request)

    def _call_sync(self, request: HttpRequest) -> HttpResponseBase:
        prepared = self._prepare_request(request)
        if isinstance(prepared, HttpResponse):
            return prepared
        tenant, urlconf, script_prefix = prepared
        with self._request_context(tenant, urlconf, script_prefix):
            response = cast(HttpResponseBase, self.get_response(request))
        return self._wrap_streaming(response, tenant, urlconf, script_prefix)

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        prepared = await self._prepare_request_async(request)
        if isinstance(prepared, HttpResponse):
            return prepared
        tenant, urlconf, script_prefix = prepared
        with self._request_context(tenant, urlconf, script_prefix):
            response = await cast(
                Awaitable[HttpResponseBase], self.get_response(request)
            )
        return self._wrap_streaming(response, tenant, urlconf, script_prefix)

    def _prepare_request(
        self, request: HttpRequest
    ) -> HttpResponse | tuple[TenantMixin | None, str | None, str]:
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            tenant = self.determine_tenant(request)
        return self._configure_request(request, tenant)

    async def _prepare_request_async(
        self, request: HttpRequest
    ) -> HttpResponse | tuple[TenantMixin | None, str | None, str]:
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            tenant = await self.determine_tenant_async(request)
        return self._configure_request(request, tenant)

    def _configure_request(
        self, request: HttpRequest, tenant: TenantMixin | None
    ) -> HttpResponse | tuple[TenantMixin | None, str | None, str]:
        if tenant and tenant.maintenance_mode:
            return HttpResponse("System Under Maintenance", status=503)

        if tenant:
            cast(Any, request).tenant = tenant
            register_tenant_database(tenant.slug)
            urlconf = conf.TENANT_URLCONF or getattr(settings, "ROOT_URLCONF", None)
            script_prefix = self._adjust_routing_for_tenant(request, tenant)
        else:
            urlconf = getattr(settings, "ROOT_URLCONF", None)
            script_prefix = get_script_prefix()

        if urlconf:
            request.urlconf = urlconf
        return tenant, urlconf, script_prefix

    @contextmanager
    def _request_context(
        self, tenant: TenantMixin | None, urlconf: str | None, script_prefix: str
    ) -> Iterator[None]:
        old_urlconf = get_urlconf()
        old_script_prefix = get_script_prefix()
        token = set_current_tenant(tenant.slug if tenant else None)
        try:
            set_urlconf(urlconf)
            set_script_prefix(script_prefix)
            yield
        finally:
            set_script_prefix(old_script_prefix)
            set_urlconf(old_urlconf)
            reset_current_tenant(token)

    def _wrap_streaming(
        self,
        response: HttpResponseBase,
        tenant: TenantMixin | None,
        urlconf: str | None,
        script_prefix: str,
    ) -> HttpResponseBase:
        if not getattr(response, "streaming", False):
            return response

        streaming_response = cast(StreamingHttpResponse, response)
        content = streaming_response.streaming_content
        if getattr(response, "is_async", False):

            async def async_content() -> AsyncIterator[bytes]:
                with self._request_context(tenant, urlconf, script_prefix):
                    async for chunk in cast(AsyncIterator[bytes], content):
                        yield chunk

            streaming_response.streaming_content = async_content()
        else:

            def sync_content() -> Iterator[bytes]:
                with self._request_context(tenant, urlconf, script_prefix):
                    yield from cast(Iterator[bytes], content)

            streaming_response.streaming_content = sync_content()
        return streaming_response

    def determine_tenant(self, request: HttpRequest) -> TenantMixin | None:
        TenantModel = get_tenant_model()
        routing_mode = conf.TENANT_ROUTING_MODE
        if routing_mode == TenantRoutingMode.SUBFOLDER:
            return self._resolve_by_subfolder(request, TenantModel)
        if routing_mode == TenantRoutingMode.DOMAIN:
            return self._resolve_by_domain(request, TenantModel)
        raise ValidationError(f"Unsupported tenant routing mode: {routing_mode!r}")

    async def determine_tenant_async(self, request: HttpRequest) -> TenantMixin | None:
        TenantModel = get_tenant_model()
        routing_mode = conf.TENANT_ROUTING_MODE
        if routing_mode == TenantRoutingMode.SUBFOLDER:
            slug = self._subfolder_slug(request)
            if not slug:
                return None
            tenant = await TenantModel.objects.filter(slug=slug).afirst()
            if tenant:
                return tenant
            raise Http404(f"No tenant with slug '{slug}'")
        if routing_mode == TenantRoutingMode.DOMAIN:
            return await self._resolve_by_domain_async(request, TenantModel)
        raise ValidationError(f"Unsupported tenant routing mode: {routing_mode!r}")

    @staticmethod
    def _host_without_port(request: HttpRequest) -> str | None:
        host = request.get_host()
        if host.startswith("["):
            return None
        name, separator, port = host.rpartition(":")
        if separator and port.isdigit():
            host = name
        try:
            return normalize_domain(host)
        except ValidationError:
            return None

    def _resolve_by_domain(
        self, request: HttpRequest, TenantModel: type[TenantMixin]
    ) -> TenantMixin | None:
        host = self._host_without_port(request)
        if not host:
            return None

        if conf.DOMAIN_MODEL:
            DomainModel = get_domain_model()
            domain_obj = (
                DomainModel.objects.filter(domain=host, is_active=True)
                .select_related("tenant")
                .first()
            )
            if domain_obj:
                return domain_obj.tenant

        configured_base = str(conf.TENANT_BASE_DOMAIN)
        if ":" in configured_base:
            configured_base = configured_base.rsplit(":", 1)[0]
        try:
            base_domain = normalize_domain(configured_base)
        except ValidationError:
            return None

        if host.endswith(f".{base_domain}"):
            slug = host[: -(len(base_domain) + 1)]
            tenant = TenantModel.objects.filter(slug=slug).first()
            if tenant:
                return tenant
            raise Http404(f"Tenant '{slug}' not found.")
        return None

    async def _resolve_by_domain_async(
        self, request: HttpRequest, TenantModel: type[TenantMixin]
    ) -> TenantMixin | None:
        host = self._host_without_port(request)
        if not host:
            return None

        if conf.DOMAIN_MODEL:
            DomainModel = get_domain_model()
            domain_obj = await (
                DomainModel.objects.filter(domain=host, is_active=True)
                .select_related("tenant")
                .afirst()
            )
            if domain_obj:
                return domain_obj.tenant

        configured_base = str(conf.TENANT_BASE_DOMAIN)
        if ":" in configured_base:
            configured_base = configured_base.rsplit(":", 1)[0]
        try:
            base_domain = normalize_domain(configured_base)
        except ValidationError:
            return None

        if host.endswith(f".{base_domain}"):
            slug = host[: -(len(base_domain) + 1)]
            tenant = await TenantModel.objects.filter(slug=slug).afirst()
            if tenant:
                return tenant
            raise Http404(f"Tenant '{slug}' not found.")
        return None

    @staticmethod
    def _subfolder_slug(request: HttpRequest) -> str | None:
        parts = request.path_info.strip("/").split("/")
        prefix = conf.TENANT_SUBFOLDER_PREFIX.strip("/")
        if prefix and len(parts) >= 2 and parts[0] == prefix:
            return parts[1]
        if not prefix and parts and parts[0]:
            return parts[0]
        return None

    def _resolve_by_subfolder(
        self, request: HttpRequest, TenantModel: type[TenantMixin]
    ) -> TenantMixin | None:
        slug = self._subfolder_slug(request)
        if not slug:
            return None
        tenant = TenantModel.objects.filter(slug=slug).first()
        if tenant:
            return tenant
        raise Http404(f"No tenant with slug '{slug}'")

    def _adjust_routing_for_tenant(
        self, request: HttpRequest, tenant: TenantMixin
    ) -> str:
        current_prefix = get_script_prefix()
        if conf.TENANT_ROUTING_MODE != TenantRoutingMode.SUBFOLDER:
            return current_prefix

        prefix = conf.TENANT_SUBFOLDER_PREFIX.strip("/")
        tenant_part = f"/{prefix}/{tenant.slug}" if prefix else f"/{tenant.slug}"
        if request.path_info != tenant_part and not request.path_info.startswith(
            f"{tenant_part}/"
        ):
            return current_prefix

        request.META["SCRIPT_NAME"] = (
            request.META.get("SCRIPT_NAME", "").rstrip("/") + tenant_part
        )
        new_path = request.path_info[len(tenant_part) :]
        request.path_info = new_path if new_path.startswith("/") else f"/{new_path}"
        return f"{current_prefix.rstrip('/')}{tenant_part}/"
