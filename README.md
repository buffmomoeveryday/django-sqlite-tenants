# Django SQLite Tenants

A lightweight, robust multi-tenancy solution for Django using SQLite. This project isolates tenant data into separate SQLite databases while maintaining a shared database for global data (tenants, users).

## Features

- **Database Isolation**: Each tenant has its own `sqlite3` database file.
- **Admin Separation**:
  - **Public Admin** (`/admin/`): Managing global entities (Tenants, Users).
  - **Tenant Admin** (`/r/<slug>/admin/`): Managing tenant-specific data within the tenant's context.
- **Strict Routing**: Database router ensures tenant apps cannot write to the shared database and vice versa.
- **Customizable**: Configurable database locations, routing modes, and app sharing.
- **Maintenance Mode**: Built-in support for tenant-specific maintenance mode.
- **Domain Support**: Multiple domain aliases per tenant with primary domain management.
- **Easy Tenant Switching**: Context manager for tenant activation in scripts and Celery tasks.

## Installation & Quick Start

1. **Install Dependencies**:
   ```bash
   uv sync
   ```

2. **Migrate System Database**:
   ```bash
   uv run python manage.py migrate
   ```

3. **Create a Tenant**:
   ```bash
   python manage.py create_tenant amazon --name "Amazon" --domain "amazon.local"
   ```

4. **Run Server**:
   ```bash
   python manage.py runserver
   ```
   - Access Public Admin: `http://localhost:8000/admin/`
   - Access Tenant Admin: `http://localhost:8000/r/amazon/admin/`

## Configuration Settings

Configure these settings in `core/settings.py` to customize the behavior of the tenant system.

### Core Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `TENANT_MODEL` | **Required** | The dotted path to your Tenant model (e.g., `"apps.tenant.CustomTenant"`). |
| `DOMAIN_MODEL` | `None` | The dotted path to your Domain model (e.g., `"apps.tenant.Domain"`). |
| `SHARED_APPS` | `[]` | List of apps that live in the **default** (shared) database (e.g., `auth`, `contenttypes`). |
| `TENANT_APPS` | `[]` | List of apps that live in the **tenant** databases (e.g., `blog`, `tenant_users`). |
| `TENANTS_DB_FOLDER` | `"tenants"` | Folder path relative to `BASE_DIR` where tenant SQLite files are stored. |

### Routing & Middleware

| Setting | Default | Description |
| :--- | :--- | :--- |
| `TENANT_ROUTING_MODE` | `"DOMAIN"` | How tenants are identified. Options:<br>• `"SUBFOLDER"`: `/r/<slug>/`<br>• `"DOMAIN"`: `<slug>.domain.com` |
| `TENANT_SUBFOLDER_PREFIX`| `"r"` | Used with `SUBFOLDER` mode. The URL prefix (e.g., `"r"` results in `/r/tenant/`). |
| `TENANT_BASE_DOMAIN` | `"localhost"|` Used with `DOMAIN` mode. The base domain to strip when identifying tenants (e.g. `tenant.example.com`). |

### URL Configuration

| Setting | Default | Description |
| :--- | :--- | :--- |
| `ROOT_URLCONF` | **Required** | URL config for the public/shared view (e.g., `"core.urls_public"`). |
| `TENANT_URLCONF` | `None` | URL config for tenant-specific views (e.g., `"core.urls_tenant"`). Swapped automatically by middleware. |

### Migration Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `AUTO_RUN_MIGRATION` | `True` | Whether to automatically run migrations when creating a tenant. |

## Application Split Example

Your `settings.py` should segregate apps to ensure proper migration and routing:

```python
SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_sqlite_tenants",
    "apps.tenant",  # The app containing the Tenant model
]

TENANT_APPS = [
    "apps.blog",         # Content specific to a tenant
    "apps.tenant_users", # Users specific to a tenant
]

# Combined for Django internals
INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

DJANGO_TENANT_SQLITE = {
    "TENANT_MODEL": "tenant.CustomTenant",
    "DOMAIN_MODEL": "tenant.Domain",
    "TENANT_URLCONF": "core.urls_tenant",
    "TENANT_ROUTING_MODE": "DOMAIN",
    "TENANT_SUBFOLDER_PREFIX": "r",
    "TENANT_BASE_DOMAIN": "localhost:8000",
}

MIDDLEWARE = [
    "django_sqlite_tenants.middlewares.TenantMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

DATABASE_ROUTERS = [
    "django_sqlite_tenants.db_routers.TenantRouter",
]
```

## Management Commands

### `create_tenant`
Creates a new tenant and initializes their database.

```bash
python manage.py create_tenant <slug> --name "Tenant Name" --domain "custom.domain.com"
```

**Arguments**:
- `<slug>`: Unique identifier for the tenant (required)
- `--name`: Display name (defaults to capitalized slug)
- `--domain`: Custom domain (optional)

**Example**:
```bash
python manage.py create_tenant apple --name "Apple Inc." --domain "apple.local"
```

### `migrate_tenant`
Runs migrations for tenant databases.

```bash
python manage.py migrate_tenant [--tenant <slug>]
```

**Options**:
- `--tenant <slug>`: Migrate only the specified tenant (optional, defaults to all tenants)

**Examples**:
```bash
# Migrate all tenants
python manage.py migrate_tenant

# Migrate specific tenant
python manage.py migrate_tenant --tenant amazon
```

## Tenant & Domain Models

### Creating Your Tenant Model

```python
# apps/tenant/models.py
from django_sqlite_tenants.models import TenantMixin

class CustomTenant(TenantMixin):
    # Add additional fields here
    industry = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
```

### Creating Your Domain Model

```python
# apps/tenant/models.py
from django_sqlite_tenants.models import DomainMixin

class Domain(DomainMixin):
    # Add additional fields here
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Domain"
        verbose_name_plural = "Domains"
```

## Usage Examples

### Accessing Tenant Data in Views

```python
from django.shortcuts import render
from apps.blog.models import Post

def blog_list(request):
    # Automatically filters posts by current tenant
    posts = Post.objects.all()
    return render(request, 'blog/list.html', {'posts': posts})
```

### Using Tenant Context Manager

```python
from apps.tenant.models import CustomTenant

def run_tenant_task():
    tenant = CustomTenant.objects.get(slug='amazon')
    
    with tenant:
        # Code here runs in the context of 'amazon' tenant
        # All database operations will use the tenant's database
        posts = Post.objects.all()
        print(f"Amazon has {len(posts)} posts")
    
    # Back to public schema
    print("Done with tenant context")
```

### Activating Tenant in Shell

```python
python manage.py shell
>>> from apps.tenant.models import CustomTenant
>>> tenant = CustomTenant.objects.get(slug='amazon')
>>> tenant.activate()
>>> # Now all queries will use Amazon's database
>>> Post.objects.count()
5
>>> CustomTenant.deactivate()  # Return to public schema
```

## Database Routing

The `TenantRouter` class handles all database routing:

- Shared apps always use the `default` database
- Tenant apps use the current tenant's database
- Relations between shared and tenant models are allowed
- Migrations are automatically routed to the correct database

## Maintenance Mode

Set a tenant to maintenance mode:

```python
from apps.tenant.models import CustomTenant

tenant = CustomTenant.objects.get(slug='amazon')
tenant.maintenance_mode = True
tenant.save()
```

When in maintenance mode, all requests will return a 503 Service Unavailable response with a simple "System Under Maintenance" message.

## Advanced Configuration

### Custom Database Location

```python
DJANGO_TENANT_SQLITE = {
    "TENANTS_DB_FOLDER": "data/tenants/databases",
    # ... other settings
}
```

### Subfolder Routing Mode

```python
DJANGO_TENANT_SQLITE = {
    "TENANT_ROUTING_MODE": "SUBFOLDER",
    "TENANT_SUBFOLDER_PREFIX": "tenants",
    # ... other settings
}
```

Tenant URLs would then be: `/tenants/amazon/blog/`

### Custom URL Confs

```python
DJANGO_TENANT_SQLITE = {
    "TENANT_URLCONF": "core.urls_tenant",
    "ROOT_URLCONF": "core.urls_public",
    # ... other settings
}
```

### Using with Celery

```python
from celery import shared_task
from apps.tenant.models import CustomTenant
from apps.blog.models import Post

@shared_task
def count_tenant_posts(tenant_slug):
    tenant = CustomTenant.objects.get(slug=tenant_slug)
    
    with tenant:
        count = Post.objects.count()
        return f"Tenant {tenant_slug} has {count} posts"
```


## Example Project

An example project is included in the `example/` directory that demonstrates:
- Tenant and Domain model implementations
- Blog application with tenant-specific content
- Tenant users management
- Admin interface customization
- Templates with tenant context

To run the example project:

```bash
cd example
uv sync
uv run python manage.py migrate
uv run python manage.py create_tenant amazon --name "Amazon" --domain "amazon.local"
uv run python manage.py runserver
```

## Testing

Run the test suite:

```bash
uv run pytest
```

Run specific tests:

```bash
uv run pytest django_sqlite_tenants/tests.py -v
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
