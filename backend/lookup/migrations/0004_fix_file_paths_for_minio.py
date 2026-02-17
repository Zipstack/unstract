"""Migration to fix file paths for MinIO storage.

This migration converts local filesystem paths to MinIO-compatible paths
for existing LookupDataSource records.

Old format: /app/prompt-studio-data/{org_id}/{project_id}/{filename}
New format: unstract/prompt-studio-data/{org_id}/{project_id}/{filename}
"""

from django.db import migrations


def fix_file_paths(apps, schema_editor):
    """Convert local paths to MinIO paths."""
    LookupDataSource = apps.get_model("lookup", "LookupDataSource")

    # Define path mappings
    old_prefix = "/app/prompt-studio-data/"
    new_prefix = "unstract/prompt-studio-data/"

    # Update file_path
    updated_count = 0
    for data_source in LookupDataSource.objects.filter(file_path__startswith=old_prefix):
        data_source.file_path = data_source.file_path.replace(old_prefix, new_prefix, 1)

        # Also fix extracted_content_path if it exists
        if (
            data_source.extracted_content_path
            and data_source.extracted_content_path.startswith(old_prefix)
        ):
            data_source.extracted_content_path = (
                data_source.extracted_content_path.replace(old_prefix, new_prefix, 1)
            )

        data_source.save(update_fields=["file_path", "extracted_content_path"])
        updated_count += 1

    if updated_count > 0:
        print(f"  Updated {updated_count} LookupDataSource records with corrected paths")


def reverse_file_paths(apps, schema_editor):
    """Revert MinIO paths back to local paths."""
    LookupDataSource = apps.get_model("lookup", "LookupDataSource")

    old_prefix = "unstract/prompt-studio-data/"
    new_prefix = "/app/prompt-studio-data/"

    for data_source in LookupDataSource.objects.filter(file_path__startswith=old_prefix):
        data_source.file_path = data_source.file_path.replace(old_prefix, new_prefix, 1)

        if (
            data_source.extracted_content_path
            and data_source.extracted_content_path.startswith(old_prefix)
        ):
            data_source.extracted_content_path = (
                data_source.extracted_content_path.replace(old_prefix, new_prefix, 1)
            )

        data_source.save(update_fields=["file_path", "extracted_content_path"])


class Migration(migrations.Migration):
    dependencies = [
        ("lookup", "0003_add_file_execution_id"),
    ]

    operations = [
        migrations.RunPython(fix_file_paths, reverse_file_paths),
    ]
