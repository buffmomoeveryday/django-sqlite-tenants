import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(unique=True)),
                ("maintenance_mode", models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name="Domain",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "domain",
                    models.CharField(
                        help_text='The domain name (e.g., "example.com" or "subdomain.example.com")',
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "is_primary",
                    models.BooleanField(
                        default=False,
                        help_text="Is this the primary domain for the tenant?",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Is this domain active and accessible?",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="tenant_registry.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Domain",
                "verbose_name_plural": "Domains",
            },
        ),
        migrations.AddConstraint(
            model_name="domain",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_primary=True),
                fields=("tenant",),
                name="tenant_registry_domain_one_primary",
            ),
        ),
    ]
