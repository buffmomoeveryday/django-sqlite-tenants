from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenant", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="domain",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="domain",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("tenant",),
                name="tenant_domain_one_primary",
            ),
        ),
    ]
