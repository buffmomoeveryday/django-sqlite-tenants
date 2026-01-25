from django_sqlite_tenants.utils import get_current_tenant_slug


def make_key(key, key_prefix, version):
    """
    Tenant aware function to generate a cache key.

    Constructs the key used by all other methods. Prepends the tenant
    `slug` and `key_prefix'.
    """
    tenant_slug = get_current_tenant_slug()
    return "%s:%s:%s:%s" % (tenant_slug or "public", key_prefix, version, key)


def reverse_key(key):
    """
    Tenant aware function to reverse a cache key.

    Required for django-redis REVERSE_KEY_FUNCTION setting.
    """
    return key.split(":", 3)[3]
