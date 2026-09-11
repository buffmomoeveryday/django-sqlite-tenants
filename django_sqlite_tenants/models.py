from contextlib import AbstractContextManager
from contextvars import ContextVar
from types import TracebackType
from typing import Any, Self

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, models, transaction

from .utils import tenant_context

_tenant_context_managers: ContextVar[
    tuple[AbstractContextManager["TenantMixin"], ...]
] = ContextVar("tenant_context_managers", default=())


class DomainMixin(models.Model):
    """Abstract domain model associated with a tenant."""

    tenant = models.ForeignKey(
        settings.DJANGO_TENANT_SQLITE["TENANT_MODEL"],
        on_delete=models.CASCADE,
        related_name="domains",
        verbose_name="Tenant",
    )
    domain = models.CharField(
        max_length=255,
        unique=True,
        help_text='The domain name (e.g., "example.com" or "subdomain.example.com")',
    )
    is_primary = models.BooleanField(
        default=False, help_text="Is this the primary domain for the tenant?"
    )
    is_active = models.BooleanField(
        default=True, help_text="Is this domain active and accessible?"
    )

    class Meta:
        abstract = True
        verbose_name = "Domain"
        verbose_name_plural = "Domains"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant",),
                condition=models.Q(is_primary=True),
                name="%(app_label)s_%(class)s_one_primary",
            )
        ]

    def __str__(self) -> str:
        return self.domain

    def clean(self) -> None:
        super().clean()
        from .provisioning import normalize_domain

        self.domain = normalize_domain(self.domain)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .provisioning import normalize_domain

        self.domain = normalize_domain(self.domain)
        database = kwargs.get("using") or self._state.db or DEFAULT_DB_ALIAS
        with transaction.atomic(using=database):
            if self.is_primary:
                self.__class__.objects.using(database).filter(  # type: ignore[attr-defined]
                    tenant=self.tenant,
                    is_primary=True,
                ).exclude(pk=self.pk).update(is_primary=False)
            super().save(*args, **kwargs)


class TenantMixin(models.Model):
    domains: models.Manager[DomainMixin]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    maintenance_mode = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.slug

    def get_primary_domain(self) -> DomainMixin | None:
        return self.domains.filter(is_primary=True, is_active=True).first()

    def get_active_domains(self) -> models.QuerySet[DomainMixin]:
        return self.domains.filter(is_active=True)

    def add_domain(
        self, domain: str, is_primary: bool = False, is_active: bool = True
    ) -> DomainMixin:
        from .provisioning import normalize_domain
        from .utils import get_domain_model

        DomainModel = get_domain_model()
        return DomainModel.objects.create(
            tenant=self,
            domain=normalize_domain(domain),
            is_primary=is_primary,
            is_active=is_active,
        )

    def __enter__(self) -> Self:
        manager = tenant_context(self)
        manager.__enter__()
        stack = _tenant_context_managers.get()
        _tenant_context_managers.set((*stack, manager))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        stack = _tenant_context_managers.get()
        if not stack:
            self.deactivate()
            return None
        manager = stack[-1]
        _tenant_context_managers.set(stack[:-1])
        return manager.__exit__(exc_type, exc_val, exc_tb)

    def activate(self) -> None:
        from .provisioning import register_tenant_database
        from .utils import set_current_tenant

        register_tenant_database(self.slug)
        set_current_tenant(self.slug)

    def clean(self) -> None:
        super().clean()
        from .provisioning import validate_tenant_slug

        validate_tenant_slug(self.slug)
        if self.pk:
            database = self._state.db or DEFAULT_DB_ALIAS
            original_slug = (
                type(self)
                .objects.using(database)
                .filter(pk=self.pk)
                .values_list("slug", flat=True)
                .first()
            )
            if original_slug is not None and self.slug != original_slug:
                raise ValidationError(
                    {"slug": "Tenant slugs are immutable after creation."}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .provisioning import validate_tenant_slug

        validate_tenant_slug(self.slug)
        if self.pk:
            database = kwargs.get("using") or self._state.db or DEFAULT_DB_ALIAS
            original_slug = (
                type(self)
                .objects.using(database)
                .filter(pk=self.pk)
                .values_list("slug", flat=True)
                .first()
            )
            if original_slug is not None and self.slug != original_slug:
                raise ValidationError(
                    {"slug": "Tenant slugs are immutable after creation."}
                )
        super().save(*args, **kwargs)

    @classmethod
    def deactivate(cls) -> None:
        from .utils import set_current_tenant

        set_current_tenant(None)
