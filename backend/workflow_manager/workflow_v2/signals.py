import logging
from typing import Any

from django.db.models import Model
from django.db.models.signals import post_save
from django.dispatch import receiver

from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.file_history import FileHistory

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkflowEndpoint)
def sync_file_reprocessing_interval(
    sender: type[Model], instance: WorkflowEndpoint, **kwargs: Any
) -> None:
    """Sync file_reprocessing_interval in FileHistory when WorkflowEndpoint settings change.

    Args:
        sender: The model class that sent the signal
        instance: The WorkflowEndpoint instance that was saved
        **kwargs: Additional arguments from the signal
    """
    # Only handle SOURCE endpoints
    if instance.endpoint_type != WorkflowEndpoint.EndpointType.SOURCE:
        return

    # Only proceed if configuration exists
    if not instance.configuration:
        return

    try:
        # Extract reprocessing configuration with proper type handling
        config: dict[str, Any] = instance.configuration or {}
        duplicate_handling: str = str(config.get("duplicateHandling", "skip_duplicates"))

        # Calculate interval in days
        reprocessing_interval: int | None = None
        if duplicate_handling == "reprocess_after_interval":
            interval_value: int = int(config.get("reprocessInterval", 0))
            interval_unit: str = str(config.get("intervalUnit", "days"))

            if interval_value > 0:
                # Convert to days
                if interval_unit == "months":
                    reprocessing_interval = interval_value * 30
                else:
                    reprocessing_interval = interval_value

        # Update all FileHistory records for this workflow
        FileHistory.objects.filter(workflow=instance.workflow).update(
            file_reprocessing_interval=reprocessing_interval
        )

    except Exception as e:
        logger.info(
            f"Could not sync file reprocessing interval for workflow {instance.workflow.id}: {e}"
        )
