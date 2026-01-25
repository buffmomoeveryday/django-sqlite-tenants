# from django.db import models
from django_sqlite_tenants.models import TenantMixin
from django_sqlite_tenants.models import DomainMixin
# Create your models here.


class CustomTenant(TenantMixin):
    pass


class Domain(DomainMixin):
    pass
