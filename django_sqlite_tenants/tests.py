from django.test import TestCase, RequestFactory
from django.conf import settings
from django.http import HttpResponse
from unittest.mock import MagicMock

from django_sqlite_tenants.utils import (
    get_current_tenant,
    set_current_tenant,
    get_current_tenant_slug,
)
from django_sqlite_tenants.middlewares import TenantMiddleware
from django_sqlite_tenants.db_routers import TenantRouter
from django_sqlite_tenants.admin_sites import tenant_admin_site, public_admin_site
from django_sqlite_tenants.models import Domain
from apps.tenant.models import CustomTenant


class TestUtils(TestCase):
    def test_set_and_get_current_tenant(self):
        # Initial state
        self.assertIsNone(get_current_tenant())
        self.assertIsNone(get_current_tenant_slug())

        # Set tenant
        set_current_tenant("test-tenant")
        self.assertEqual(get_current_tenant_slug(), "test-tenant")

    def test_get_tenant_object(self):
        tenant = CustomTenant.objects.create(name="Test", slug="test-obj")
        Domain.objects.create(tenant=tenant, domain="test.local", is_primary=True)
        set_current_tenant("test-obj")

        # Test get_current_tenant returns the object
        tenant_obj = get_current_tenant()
        self.assertIsNotNone(tenant_obj)
        self.assertEqual(tenant_obj.slug, "test-obj")

        # Clean up
        set_current_tenant(None)


class TestDomainModel(TestCase):
    def test_domain_creation(self):
        tenant = CustomTenant.objects.create(name="Test Tenant", slug="test-tenant")
        domain = Domain.objects.create(
            tenant=tenant, domain="test.example.com", is_primary=True, is_active=True
        )

        self.assertEqual(domain.tenant, tenant)
        self.assertEqual(domain.domain, "test.example.com")
        self.assertTrue(domain.is_primary)
        self.assertTrue(domain.is_active)

    def test_primary_domain_constraint(self):
        tenant = CustomTenant.objects.create(name="Test Tenant", slug="test-tenant")
        domain1 = Domain.objects.create(
            tenant=tenant, domain="domain1.com", is_primary=True, is_active=True
        )
        domain2 = Domain.objects.create(
            tenant=tenant, domain="domain2.com", is_primary=True, is_active=True
        )

        # Check that only domain2 is primary
        domain1.refresh_from_db()
        domain2.refresh_from_db()
        self.assertFalse(domain1.is_primary)
        self.assertTrue(domain2.is_primary)

    def test_tenant_domain_relationship(self):
        tenant = CustomTenant.objects.create(name="Test Tenant", slug="test-tenant")
        Domain.objects.create(tenant=tenant, domain="domain1.com", is_primary=True)
        Domain.objects.create(tenant=tenant, domain="domain2.com", is_primary=False)

        # Check tenant has both domains
        self.assertEqual(tenant.domains.count(), 2)
        self.assertTrue(tenant.domains.filter(domain="domain1.com").exists())
        self.assertTrue(tenant.domains.filter(domain="domain2.com").exists())

    def test_get_primary_domain(self):
        tenant = CustomTenant.objects.create(name="Test Tenant", slug="test-tenant")
        Domain.objects.create(tenant=tenant, domain="domain1.com", is_primary=True)
        Domain.objects.create(tenant=tenant, domain="domain2.com", is_primary=False)

        self.assertEqual(tenant.get_primary_domain().domain, "domain1.com")

    def test_get_active_domains(self):
        tenant = CustomTenant.objects.create(name="Test Tenant", slug="test-tenant")
        Domain.objects.create(
            tenant=tenant, domain="active.com", is_primary=True, is_active=True
        )
        Domain.objects.create(
            tenant=tenant, domain="inactive.com", is_primary=False, is_active=False
        )

        active_domains = list(tenant.get_active_domains())
        self.assertEqual(len(active_domains), 1)
        self.assertEqual(active_domains[0].domain, "active.com")


class TestTenantRouter(TestCase):
    def setUp(self):
        self.router = TenantRouter()
        self.tenant_slug = "router-test"
        self.old_shared = getattr(settings, "SHARED_APPS", [])
        self.old_tenant = getattr(settings, "TENANT_APPS", [])

    def tearDown(self):
        settings.SHARED_APPS = self.old_shared
        settings.TENANT_APPS = self.old_tenant

    def test_db_for_read_shared_app(self):
        # Shared app (e.g. auth) should go to default
        MockModel = MagicMock()
        MockModel._meta.app_label = "auth"

        settings.SHARED_APPS = ["django.contrib.auth"]
        db = self.router.db_for_read(MockModel)
        self.assertEqual(db, "default")

    def test_db_for_read_tenant_app(self):
        # Tenant app should go to tenant DB if tenant is active
        MockModel = MagicMock()
        MockModel._meta.app_label = "blog"

        settings.SHARED_APPS = ["django.contrib.auth"]
        settings.TENANT_APPS = ["apps.blog"]

        # Case 1: No active tenant -> default
        set_current_tenant(None)
        db = self.router.db_for_read(MockModel)
        self.assertEqual(db, "default")

        # Case 2: Active tenant -> tenant_slug
        set_current_tenant(self.tenant_slug)
        db = self.router.db_for_read(MockModel)
        self.assertEqual(db, self.tenant_slug)

        # Clean up
        set_current_tenant(None)

    def test_allow_migrate(self):
        settings.SHARED_APPS = ["django.contrib.auth"]
        settings.TENANT_APPS = ["apps.blog"]

        # Default DB: allow shared, deny tenant
        self.assertTrue(self.router.allow_migrate("default", "auth"))
        self.assertFalse(self.router.allow_migrate("default", "blog"))

        # Tenant DB: deny shared, allow tenant
        self.assertFalse(self.router.allow_migrate("some_tenant", "auth"))
        self.assertTrue(self.router.allow_migrate("some_tenant", "blog"))


class TestAdminSeparation(TestCase):
    def test_admin_sites_exist(self):
        self.assertIsNotNone(tenant_admin_site)
        self.assertIsNotNone(public_admin_site)
        self.assertEqual(tenant_admin_site.name, "tenant_admin")
        self.assertEqual(public_admin_site.name, "public_admin")
