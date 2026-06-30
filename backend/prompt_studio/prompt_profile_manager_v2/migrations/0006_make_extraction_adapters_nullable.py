import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0001_initial"),
        ("prompt_profile_manager_v2", "0005_profilemanager_shared_to_org_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profilemanager",
            name="vector_store",
            field=models.ForeignKey(
                blank=True,
                db_comment="Field to store the chosen vector store.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles_vector_store",
                to="adapter_processor_v2.adapterinstance",
            ),
        ),
        migrations.AlterField(
            model_name="profilemanager",
            name="embedding_model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles_embedding_model",
                to="adapter_processor_v2.adapterinstance",
            ),
        ),
        migrations.AlterField(
            model_name="profilemanager",
            name="x2text",
            field=models.ForeignKey(
                blank=True,
                db_comment="Field to store the X2Text Adapter chosen by the user",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles_x2text",
                to="adapter_processor_v2.adapterinstance",
            ),
        ),
    ]
