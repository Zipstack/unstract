# Generated by Django 4.2.1 on 2025-01-16 10:19

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("account_v2", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        db_comment="Unique name of the tag", max_length=50
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, db_comment="Description of the tag", null=True
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tag",
                "verbose_name_plural": "Tags",
                "db_table": "tag",
            },
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                fields=("name", "organization"), name="unique_tag_name_organization"
            ),
        ),
    ]