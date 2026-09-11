import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections, transaction

from .conf import conf
from .models import TenantMixin
from .utils import get_domain_model, get_tenant_model, tenant_context

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_database_lock = threading.RLock()
_tenant_aliases: set[str] = set()
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_tenant_slug(slug: str) -> str:
    """Return a safe tenant slug or raise ``ValidationError``."""
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise ValidationError(
            "Tenant slugs must be lowercase DNS labels containing only letters, "
            "numbers, and interior hyphens (maximum 63 characters)."
        )
    if slug == DEFAULT_DB_ALIAS:
        raise ValidationError(f"'{DEFAULT_DB_ALIAS}' is a reserved tenant slug.")

    with _database_lock:
        if slug in settings.DATABASES and slug not in _tenant_aliases:
            raise ValidationError(
                f"'{slug}' conflicts with a configured database alias."
            )
    return slug


def normalize_domain(domain: str) -> str:
    """Normalize an internationalized hostname to lowercase ASCII."""
    if not isinstance(domain, str):
        raise ValidationError("Domain must be a string.")
    value = domain.strip().rstrip(".")
    if not value or "://" in value or any(char in value for char in "/\\:@"):
        raise ValidationError(
            "Enter a hostname without a scheme, port, path, or credentials."
        )
    try:
        value = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValidationError("Enter a valid domain name.") from exc
    if len(value) > 253 or any(
        not _DOMAIN_LABEL_RE.fullmatch(label) for label in value.split(".")
    ):
        raise ValidationError("Enter a valid domain name.")
    return value


def get_tenant_database_directory() -> Path:
    folder = Path(conf.TENANTS_DB_FOLDER)
    if folder.is_absolute():
        raise ImproperlyConfigured("TENANTS_DB_FOLDER must be relative to BASE_DIR.")

    base_dir = Path(settings.BASE_DIR).resolve()
    tenant_dir = (base_dir / folder).resolve()
    if tenant_dir != base_dir and base_dir not in tenant_dir.parents:
        raise ImproperlyConfigured("TENANTS_DB_FOLDER must remain inside BASE_DIR.")
    return tenant_dir


def get_tenant_database_path(slug: str) -> Path:
    slug = validate_tenant_slug(slug)
    tenant_dir = get_tenant_database_directory()
    path = (tenant_dir / f"{slug}.sqlite3").resolve()
    if path.parent != tenant_dir:
        raise ValidationError("Tenant database path escapes TENANTS_DB_FOLDER.")
    return path


def _database_config(path: Path) -> dict[str, Any]:
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(path),
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
        "TIME_ZONE": getattr(settings, "TIME_ZONE", None),
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {
            "CHARSET": None,
            "COLLATION": None,
            "MIGRATE": True,
            "MIRROR": None,
            "NAME": None,
        },
    }


def register_tenant_database(slug: str) -> str:
    """Register and return a validated tenant database alias."""
    path = get_tenant_database_path(slug)
    if not path.is_file():
        raise FileNotFoundError(
            f"Tenant database for '{slug}' has not been provisioned."
        )
    with _database_lock:
        if slug in _tenant_aliases:
            configured = Path(connections.databases[slug]["NAME"]).resolve()
            if configured != path:
                raise ImproperlyConfigured(
                    f"Tenant alias '{slug}' is already registered for another path."
                )
            return slug

        if slug in connections.databases:
            raise ImproperlyConfigured(
                f"Tenant slug '{slug}' conflicts with a configured database alias."
            )
        connections.databases[slug] = _database_config(path)
        _tenant_aliases.add(slug)
    return slug


def is_tenant_database_alias(alias: str) -> bool:
    with _database_lock:
        return alias in _tenant_aliases


def reserve_tenant_database(slug: str) -> Path:
    """Atomically reserve a new tenant database filename."""
    path = get_tenant_database_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(candidate.exists() for candidate in tenant_database_files(path)):
        raise FileExistsError(f"Database files already exist for tenant '{slug}'.")
    try:
        path.touch(exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Database files already exist for tenant '{slug}'."
        ) from exc
    return path


def unregister_tenant_database(slug: str) -> None:
    """Close and remove a dynamically registered tenant connection."""
    with _database_lock:
        if slug not in _tenant_aliases:
            return
        local_connections = cast(Any, connections)._connections
        connection = getattr(local_connections, slug, None)
        if connection is not None:
            connection.close()
            delattr(local_connections, slug)
        connections.databases.pop(slug, None)
        _tenant_aliases.discard(slug)


def tenant_database_files(path: Path) -> Iterator[Path]:
    yield path
    yield Path(f"{path}-wal")
    yield Path(f"{path}-shm")


def remove_tenant_database_files(path: Path, *, include_backup: bool = False) -> None:
    for candidate in tenant_database_files(path):
        candidate.unlink(missing_ok=True)
    if include_backup:
        Path(f"{path}.bak").unlink(missing_ok=True)


def create_tenant(
    *, slug: str, name: str, domain: str | None = None, **fields: Any
) -> TenantMixin:
    """Create shared tenant metadata and provision a fresh tenant database."""
    slug = validate_tenant_slug(slug)
    path = get_tenant_database_path(slug)
    TenantModel = get_tenant_model()

    if TenantModel.objects.using(DEFAULT_DB_ALIAS).filter(slug=slug).exists():
        raise ValidationError(f"Tenant '{slug}' already exists.")
    path = reserve_tenant_database(slug)
    try:
        alias = register_tenant_database(slug)
        with tenant_context(slug):
            call_command("migrate", database=alias, interactive=False, verbosity=0)
        connections[alias].close()
        with transaction.atomic(using=DEFAULT_DB_ALIAS):
            tenant = TenantModel.objects.using(DEFAULT_DB_ALIAS).create(
                slug=slug, name=name, **fields
            )
            if domain:
                DomainModel = get_domain_model()
                DomainModel.objects.using(DEFAULT_DB_ALIAS).create(
                    tenant=tenant,
                    domain=normalize_domain(domain),
                    is_primary=True,
                    is_active=True,
                )
        return tenant
    except Exception:
        unregister_tenant_database(slug)
        remove_tenant_database_files(path)
        raise
