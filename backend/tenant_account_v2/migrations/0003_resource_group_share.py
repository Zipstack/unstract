"""Create the polymorphic ``ResourceGroupShare`` table (UN-2977).

This is the single new migration for group-based resource sharing. PR
#1986's per-resource ``shared_groups`` M2M was scrapped in favor of one
polymorphic table covering all shareable resources, so there is no
per-resource ``AddField``/``RemoveField`` cycle and no data backfill —
nothing existed to migrate from.

The migration depends on each in-scope resource app's latest
pre-shared_groups migration so it sits at the *top* of the dependency
graph for those apps (resource migrations are below this one).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("tenant_account_v2", "0002_organization_group_group_membership"),
        ("pipeline_v2", "0003_add_sharing_fields_to_pipeline"),
        ("workflow_v2", "0019_remove_filehistory_trigram_index"),
        ("api_v2", "0003_add_organization_rate_limit"),
        ("adapter_processor_v2", "0003_mark_deprecated_adapters"),
        ("connector_v2", "0005_fix_unintended_connector_sharing"),
        ("prompt_studio_core_v2", "0007_customtool_last_exported_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResourceGroupShare",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("object_id", models.CharField(max_length=255)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="resource_shares",
                        to="tenant_account_v2.organizationgroup",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="resource_group_shares",
                        to="account_v2.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Resource Group Share",
                "verbose_name_plural": "Resource Group Shares",
                "db_table": "resource_group_share",
            },
        ),
        migrations.AddConstraint(
            model_name="resourcegroupshare",
            constraint=models.UniqueConstraint(
                fields=("group", "content_type", "object_id"),
                name="uniq_resource_group_share",
            ),
        ),
        migrations.AddIndex(
            model_name="resourcegroupshare",
            index=models.Index(
                fields=["content_type", "object_id"],
                name="resource_gr_content_8c9a73_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="resourcegroupshare",
            index=models.Index(
                fields=["organization", "group"],
                name="resource_gr_organiz_d77c32_idx",
            ),
        ),
    ]
