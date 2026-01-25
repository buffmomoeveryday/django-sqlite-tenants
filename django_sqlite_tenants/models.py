# django_sqlite_tenants/models.py
from django_sqlite_tenants.utils import get_current_tenant_slug, set_current_tenant
from django.db import models

from django.conf import settings


class DomainMixin(models.Model):
    """
    Represents a domain associated with a tenant.
    A tenant can have multiple domains, including subdomains and custom domains.
    This is an abstract model that should be inherited by your domain model.
    """

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
        unique_together = ("tenant", "domain")

    def __str__(self):
        return self.domain

    def save(self, *args, **kwargs):
        # Ensure only one primary domain per tenant
        if self.is_primary:
            self.__class__.objects.filter(  # type:ignore
                tenant=self.tenant,
                is_primary=True,
            ).exclude(id=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class TenantMixin(models.Model):
    domains: models.Manager[DomainMixin]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    maintenance_mode = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def __str__(self):
        return self.slug

    def get_primary_domain(self):
        """Get the primary domain for this tenant."""
        return self.domains.filter(
            is_primary=True,
            is_active=True,
        ).first()

    def get_active_domains(self):
        """Get all active domains for this tenant."""
        return self.domains.filter(is_active=True)

    def add_domain(self, domain, is_primary=False, is_active=True):
        """Add a new domain to this tenant."""
        from django_sqlite_tenants.utils import get_domain_model

        DomainModel = get_domain_model()
        return DomainModel.objects.create(
            tenant=self,
            domain=domain,
            is_primary=is_primary,
            is_active=is_active,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize previous tenant stack for context manager
        if not hasattr(self, "_previous_tenant"):
            self._previous_tenant = []
        # Store original slug for tracking changes
        self._original_slug = self.slug

    def __enter__(self):
        """
        Syntax sugar which helps in celery tasks, cron jobs, and other scripts

        Usage:
            with Tenant.objects.get(slug='test') as tenant:
                # run some code in tenant test
            # run some code in previous tenant (public probably)
        """
        # Save previous tenant slug

        self._previous_tenant.append(get_current_tenant_slug())
        self.activate()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._previous_tenant:
            set_current_tenant(self._previous_tenant.pop())
        else:
            self.deactivate()

    def activate(self):
        """
        Syntax sugar that helps at django shell with fast tenant changing

        Usage:
            Tenant.objects.get(slug='test').activate()
        """

        set_current_tenant(self.slug)

    def save(self, *args, **kwargs):
        """
        Override save method to handle slug renaming.
        """
        # Check if slug has changed
        slug_changed = False
        if self.pk:
            slug_changed = self.slug != self._original_slug

        # Call parent class save method
        super().save(*args, **kwargs)

        # If slug changed and it's not a new instance, rename the database file
        if slug_changed:
            from django_sqlite_tenants.utils import rename_tenant_database

            rename_tenant_database(self._original_slug, self.slug)

        # Update original slug for next save
        self._original_slug = self.slug

    @classmethod
    def deactivate(cls):
        """
        Syntax sugar, return to public schema

        Usage:
            test_tenant.deactivate()
            # or simpler
            Tenant.deactivate()
        """
        set_current_tenant(None)
