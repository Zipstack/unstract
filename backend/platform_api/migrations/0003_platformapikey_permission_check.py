from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_api", "0002_add_full_access_permission"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="platformapikey",
            constraint=models.CheckConstraint(
                check=models.Q(permission__in=["read", "read_write", "full_access"]),
                name="platform_api_key_permission_valid",
            ),
        ),
    ]
