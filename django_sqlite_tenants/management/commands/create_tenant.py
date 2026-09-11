from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from django_sqlite_tenants.provisioning import create_tenant


class Command(BaseCommand):
    help = "Create tenant metadata and provision a new isolated SQLite database."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("slug", help="Lowercase DNS-safe tenant identifier")
        parser.add_argument("--name", help="Display name (defaults to slug)")
        parser.add_argument("--domain", help="Primary custom hostname")

    def handle(self, *args: Any, **options: Any) -> None:
        slug = options["slug"]
        name = options.get("name") or slug
        self.stdout.write(f"Provisioning tenant '{name}' ({slug})...")
        try:
            tenant = create_tenant(
                slug=slug,
                name=name,
                domain=options.get("domain"),
            )
        except (ValidationError, FileExistsError) as exc:
            messages = getattr(exc, "messages", None)
            raise CommandError("; ".join(messages) if messages else str(exc)) from exc
        except Exception as exc:
            raise CommandError(f"Tenant provisioning failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Tenant '{tenant.slug}' is ready."))
