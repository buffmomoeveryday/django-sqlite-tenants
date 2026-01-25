# Django SQLite Tenants

A lightweight, robust multi-tenancy solution for Django using SQLite. This project isolates tenant data into separate SQLite databases while maintaining a shared database for global data (tenants, users).

## Features

-   **Database Isolation**: Each tenant has its own `sqlite3` database file.
-   **Admin Separation**:
    -   **Public Admin** (`/admin/`): Managing global entities (Tenants, Users).
    -   **Tenant Admin** (`/r/<slug>/admin/`): Managing tenant-specific data within the tenant's context.
-   **Strict Routing**: Database router ensures tenant apps cannot write to the shared database and vice versa.
-   **Customizable**: Configurable database locations, routing modes, and app sharing.

## Installation & Quick Start

1.  **Install Dependencies**:
    ```bash
    uv sync
    ```

2.  **Migrate System Database**:
    ```bash
    uv run python manage.py migrate
    ```

3.  **Create a Tenant**:
    ```bash
    python manage.py shell
    >>> from apps.tenant.models import CustomTenant
    >>> CustomTenant.objects.create(name="Amazon", slug="amazon", domain="amazon.local")
    ```

4.  **Migrate Tenant Database**:
    ```bash
    python manage.py migrate_tenant --tenant amazon
    ```

5.  **Run Server**:
    ```bash
    python manage.py runserver
    ```
    -   Access Public Admin: `http://localhost:8000/admin/`
    -   Access Tenant Admin: `http://localhost:8000/r/amazon/admin/`

## Configuration Settings

Configure these settings in `core/settings.py` to customize the behavior of the tenant system.

### Core Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `TENANT_MODEL` | **Required** | The dotted path to your Tenant model (e.g., `"apps.tenant.CustomTenant"`). |
| `SHARED_APPS` | `[]` | List of apps that live in the **default** (shared) database (e.g., `auth`, `contenttypes`). |
| `TENANT_APPS` | `[]` | List of apps that live in the **tenant** databases (e.g., `blog`, `tenant_users`). |
| `TENANTS_DB_FOLDER` | `"tenants"` | Folder path relative to `BASE_DIR` where tenant SQLite files are stored. |

### Routing & Middleware

| Setting | Default | Description |
| :--- | :--- | :--- |
| `TENANT_ROUTING_MODE` | `"DOMAIN"` | How tenants are identified. Options:<br>• `"SUBFOLDER"`: `/r/<slug>/`<br>• `"DOMAIN"`: `<slug>.domain.com` |
| `TENANT_SUBFOLDER_PREFIX`| `None` | Used with `SUBFOLDER` mode. The URL prefix (e.g., `"r"` results in `/r/tenant/`). |
| `TENANT_BASE_DOMAIN` | `"localhost"`| Used with `DOMAIN` mode. The base domain to strip when identifying tenants (e.g. `tenant.example.com`). |

### URL Configuration

| Setting | Default | Description |
| :--- | :--- | :--- |
| `ROOT_URLCONF` | **Required** | URL config for the public/shared view (e.g., `"core.urls_public"`). |
| `TENANT_URLCONF` | `None` | URL config for tenant-specific views (e.g., `"core.urls_tenant"`). Swapped automatically by middleware. |

## Application Split Example

Your `settings.py` should segregate apps to ensure proper migration and routing:

```python
SHARED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
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
```

## Management Commands

-   `migrate_tenant`: Runs migrations for a specific tenant database.
    ```bash
    python manage.py migrate_tenant --tenant <slug>
    ```
