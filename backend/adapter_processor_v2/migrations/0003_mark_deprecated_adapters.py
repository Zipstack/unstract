# Data migration to mark deprecated adapters as unavailable

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Deprecated adapters mapping: adapter_id|UUID -> metadata
DEPRECATED_ADAPTERS = {
    "noOpEmbedding|ff223003-fee8-4079-b288-e86215e6b39a": {
        "reason": "No-op adapter deprecated - not for production use",
        "deprecated_date": "2024-11-24",
        "adapter_name": "noOpEmbedding",
        "adapter_type": "EMBEDDING",
    },
    "palm|af7c8ee7-3d01-47c5-9b81-5ffd7546014b": {
        "reason": "Google PaLM API sunset - replaced by Gemini",
        "deprecated_date": "2024-11-24",
        "replacement_adapter": "gemini",
        "adapter_name": "palm",
        "adapter_type": "LLM",
    },
    "noOpLlm|f673a5a2-90f9-40f5-94c0-9fbc663b7553": {
        "reason": "No-op adapter deprecated - not for production use",
        "deprecated_date": "2024-11-24",
        "adapter_name": "noOpLlm",
        "adapter_type": "LLM",
    },
    "qdrantfastembed|31e83eee-a416-4c07-9c9c-02392d5bcf7f": {
        "reason": "Qdrant FastEmbed deprecated - use standard Qdrant adapter",
        "deprecated_date": "2024-11-24",
        "replacement_adapter": "qdrant",
        "adapter_name": "qdrantfastembed",
        "adapter_type": "VECTOR_DB",
    },
    "palm|a3fc9fda-f02f-405f-bb26-8bd2ace4317e": {
        "reason": "Google PaLM API sunset - replaced by Gemini",
        "deprecated_date": "2024-11-24",
        "replacement_adapter": "gemini",
        "adapter_name": "palm",
        "adapter_type": "EMBEDDING",
    },
}


def mark_deprecated_adapters(apps, schema_editor):
    """Mark deprecated adapters as unavailable and store their metadata."""
    AdapterInstance = apps.get_model("adapter_processor_v2", "AdapterInstance")

    marked_count = 0
    not_found_count = 0

    for adapter_key, deprecation_info in DEPRECATED_ADAPTERS.items():
        try:
            # The adapter_id column stores the full "name|uuid" format
            adapter = AdapterInstance.objects.filter(adapter_id=adapter_key).first()

            if adapter:
                # Mark as unavailable
                adapter.is_available = False
                adapter.deprecation_metadata = deprecation_info
                adapter.save(update_fields=["is_available", "deprecation_metadata"])

                marked_count += 1
                logger.info(
                    f"Marked adapter '{adapter.adapter_name}' (ID: {adapter.id}) "
                    f"as unavailable. Reason: {deprecation_info['reason']}"
                )
            else:
                not_found_count += 1
                logger.info(
                    f"Adapter not found in database: {adapter_key}. "
                    "This is expected if the adapter was never created."
                )

        except Exception as e:
            logger.error(
                f"Error processing adapter {adapter_key}: {e}"
            )

    logger.info(
        f"Deprecation migration completed. "
        f"Marked {marked_count} adapters as unavailable. "
        f"{not_found_count} adapters not found (expected for never-created adapters)."
    )


def reverse_deprecation(apps, schema_editor):
    """Reverse the deprecation marking (for rollback purposes)."""
    AdapterInstance = apps.get_model("adapter_processor_v2", "AdapterInstance")

    # Get all adapter_ids from deprecated adapters (full "name|uuid" format)
    deprecated_adapter_ids = list(DEPRECATED_ADAPTERS.keys())

    # Reset is_available and clear deprecation_metadata
    updated = AdapterInstance.objects.filter(
        adapter_id__in=deprecated_adapter_ids
    ).update(
        is_available=True,
        deprecation_metadata=None
    )

    logger.info(f"Reversed deprecation for {updated} adapters")


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0002_add_adapter_availability_fields"),
    ]

    operations = [
        migrations.RunPython(mark_deprecated_adapters, reverse_deprecation),
    ]
