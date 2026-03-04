# Generated manually - Remove reference_data_type field from LookupProject

from django.db import migrations


class Migration(migrations.Migration):
    """Remove reference_data_type field from LookupProject model.

    This field is no longer needed as the type categorization
    has been removed from the Lookup projects feature.
    """

    dependencies = [
        ("lookup", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="lookupproject",
            name="reference_data_type",
        ),
    ]
