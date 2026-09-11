# Django SQLite Tenants

Database-per-tenant isolation for Django projects backed by SQLite. Shared apps
use the default database; explicitly configured tenant apps use one SQLite file
per tenant.

> This package is pre-1.0. The current release hardens tenant isolation and
> intentionally makes tenant slugs immutable.

## Requirements

- Python 3.11 or newer
- Django 5.2 or 6.x

```bash
pip install django-sqlite-tenants
```

## Configuration

Define shared and tenant applications separately, combine them for Django, and
install the router and middleware:

```python
SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_sqlite_tenants",
    "apps.tenant",
]
TENANT_APPS = ["apps.blog"]
INSTALLED_APPS = SHARED_APPS + TENANT_APPS

DJANGO_TENANT_SQLITE = {
    "TENANT_MODEL": "tenant.Tenant",
    "DOMAIN_MODEL": "tenant.Domain",  # optional in subdomain-only setups
    "TENANT_URLCONF": "core.urls_tenant",
    "TENANT_ROUTING_MODE": "DOMAIN",  # DOMAIN or SUBFOLDER
    "TENANT_BASE_DOMAIN": "example.com",
    "TENANT_SUBFOLDER_PREFIX": "r",
    "TENANTS_DB_FOLDER": "tenants",  # relative to BASE_DIR
}

MIDDLEWARE = [
    "django_sqlite_tenants.middlewares.TenantMiddleware",
    # the remaining Django middleware...
]
DATABASE_ROUTERS = ["django_sqlite_tenants.db_routers.TenantRouter"]
```

The middleware should be first so every downstream database access has an
established tenant context. `SHARED_APPS` and `TENANT_APPS` must not overlap.
Unknown apps are left to other routers; tenant apps fail closed when no tenant
is active.

Concrete registry models inherit the supplied abstract models:

```python
from django_sqlite_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    pass


class Domain(DomainMixin):
    pass
```

Run `makemigrations` in the application containing these concrete models. The
domain mixin adds a conditional database constraint guaranteeing at most one
primary domain per tenant.

## Provisioning and use

Provisioning is explicit. Saving a tenant model directly creates registry
metadata only; it does not run migrations.

```bash
python manage.py migrate
python manage.py create_tenant acme --name "Acme" --domain acme.example.com
```

Application code can use the same service:

```python
from django_sqlite_tenants.provisioning import create_tenant

tenant = create_tenant(slug="acme", name="Acme", domain="acme.example.com")
```

Slugs are lowercase DNS labels, are used as database aliases and filenames,
and cannot be changed after creation. Existing database files are never adopted
by a newly created tenant.

For scripts and task workers, activate a tenant with a task-local context:

```python
from django_sqlite_tenants.utils import tenant_context

with tenant_context("acme"):
    Post.objects.create(title="Tenant data")
```

`with tenant:` remains supported. Context is isolated across asynchronous tasks
and restored after nested contexts and exceptions.

## Migrations and recovery

```bash
python manage.py migrate_tenant
python manage.py migrate_tenant --tenant acme
```

Existing databases are backed up through SQLite's online backup API before
migration. Successful migrations remove the backup and maintenance mode. If a
migration fails, the command continues with other tenants, exits non-zero, keeps
the failed tenant in maintenance mode, and preserves `<slug>.sqlite3.bak`.

Restore a backup only while all application workers that can access that tenant
are stopped. Never replace a live WAL-mode database file. After restoring,
restart workers and clear maintenance mode only after validating the schema and
data.

Deleting a tenant registry record intentionally does not delete its database.
After confirming the record is gone, purge an orphan explicitly:

```bash
python manage.py purge_tenant_database acme --yes
```

This permanently removes the database, WAL/SHM files, and preserved backup.

## Isolation limitations

- Django foreign keys cannot cross SQLite databases. Do not define tenant-model
  foreign keys to shared models; store an immutable shared identifier instead.
- Shared authentication means the same account registry is visible to all
  tenants unless the project implements tenant-aware authorization.
- SQLite is appropriate for modest write concurrency. Operational backups and
  schema recovery still require normal process-level coordination.
- `QuerySet.update()`, bulk SQL, and direct database writes bypass model-level
  slug immutability and are unsupported for tenant registry rows.

## Admin and caching

`public_admin_site` and `tenant_admin_site` are separate Django admin registries
using stock Django templates. Register shared models only on the public site and
tenant models only on the tenant site.

For tenant-aware Django cache keys:

```python
CACHES = {
    "default": {
        # backend settings...
        "KEY_FUNCTION": "django_sqlite_tenants.cache.make_key",
    }
}
```

## Development

```bash
uv sync
uv run ruff check .
uv run ty check
uv run python -m django test --settings=tests.settings
uv build
```

The CI matrix covers Python 3.11–3.13 across compatible Django 5.2 and 6.x
releases. Publishing occurs only from a `v<project-version>` tag after every
matrix job passes.
