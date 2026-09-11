from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DEFAULT_DB_ALIAS

from django_sqlite_tenants.provisioning import (
    get_tenant_database_path,
    remove_tenant_database_files,
    tenant_lifecycle_lock,
    unregister_tenant_database,
    validate_tenant_slug,
)
from django_sqlite_tenants.utils import get_tenant_model


class Command(BaseCommand):
    help = "Permanently purge database files for a tenant whose record was deleted."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("slug")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm permanent deletion of database, WAL, and backup files",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        slug = validate_tenant_slug(options["slug"])
        if not options["yes"]:
            raise CommandError("Pass --yes to confirm permanent deletion.")

        with tenant_lifecycle_lock(slug):
            TenantModel = get_tenant_model()
            if TenantModel.objects.using(DEFAULT_DB_ALIAS).filter(slug=slug).exists():
                raise CommandError(
                    f"Tenant '{slug}' still exists; delete its shared record first."
                )

            path = get_tenant_database_path(slug)
            candidates = [
                path,
                Path(f"{path}-wal"),
                Path(f"{path}-shm"),
                Path(f"{path}.bak"),
            ]
            existing = [candidate for candidate in candidates if candidate.exists()]
            if not existing:
                raise CommandError(f"No database files found for tenant '{slug}'.")

            unregister_tenant_database(slug)
            remove_tenant_database_files(path, include_backup=True)
        self.stdout.write(self.style.SUCCESS(f"Purged database files for '{slug}'."))
