# Generated migration for adding reindex_required field to LookupIndexManager

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add reindex_required field to LookupIndexManager.

    This field tracks whether indexes are stale and need re-indexing
    when profile settings change (chunk_size, embedding_model, etc.).
    """

    dependencies = [
        ("lookup", "0004_fix_file_paths_for_minio"),
    ]

    operations = [
        migrations.AddField(
            model_name="lookupindexmanager",
            name="reindex_required",
            field=models.BooleanField(
                default=False,
                db_comment="Flag indicating indexes are stale and need re-indexing",
                help_text="Set to True when profile settings change and re-indexing is needed",
            ),
        ),
    ]
