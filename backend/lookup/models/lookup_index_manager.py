"""LookupIndexManager model for tracking indexed reference data."""

import logging
import uuid

from account_v2.models import User
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from utils.models.base_model import BaseModel
from utils.user_context import UserContext

from unstract.sdk1.constants import LogLevel
from unstract.sdk1.vector_db import VectorDB

logger = logging.getLogger(__name__)


class LookupIndexManager(BaseModel):
    """Model to store indexing details for Look-Up reference data.

    Tracks which data sources have been indexed with which profile,
    stores vector DB index IDs, and manages extraction status.

    Follows the same pattern as Prompt Studio's IndexManager.
    """

    index_manager_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    # Reference to the data source being indexed
    data_source = models.ForeignKey(
        "LookupDataSource",
        on_delete=models.CASCADE,
        related_name="index_managers",
        editable=False,
        null=False,
        blank=False,
        db_comment="Reference data source being indexed",
    )

    # Reference to the profile used for indexing
    profile_manager = models.ForeignKey(
        "LookupProfileManager",
        on_delete=models.SET_NULL,
        related_name="index_managers",
        editable=False,
        null=True,
        blank=True,
        db_comment="Profile used for indexing this data source",
    )

    # Vector DB index ID for this data source (raw index)
    raw_index_id = models.CharField(
        max_length=255,
        db_comment="Raw index ID for vector DB",
        editable=False,
        null=True,
        blank=True,
    )

    # History of all index IDs (for cleanup on deletion)
    index_ids_history = models.JSONField(
        db_comment="List of all index IDs created for this data source",
        default=list,
        null=False,
        blank=False,
    )

    # Extraction status per X2Text configuration
    # Format: {x2text_config_hash: {"extracted": bool, "enable_highlight": bool, "error": str|null}}
    extraction_status = models.JSONField(
        db_comment='Extraction status per X2Text config: {x2text_config_hash: {"extracted": bool, "enable_highlight": bool, "error": str}}',
        default=dict,
        null=False,
        blank=False,
    )

    # Overall extraction and indexing status (legacy field, kept for compatibility)
    # Format: {"extracted": bool, "indexed": bool, "error": str|null}
    status = models.JSONField(
        db_comment="Extraction and indexing status", null=False, blank=False, default=dict
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_index_managers_created",
        null=True,
        blank=True,
        editable=False,
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_index_managers_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Lookup Index Manager"
        verbose_name_plural = "Lookup Index Managers"
        db_table = "lookup_index_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["data_source", "profile_manager"],
                name="unique_data_source_profile_manager_index",
            ),
        ]

    def __str__(self):
        return f"Index for {self.data_source.file_name} with {self.profile_manager.profile_name if self.profile_manager else 'No Profile'}"


def delete_from_vector_db(index_ids_history, vector_db_instance_id):
    """Delete index IDs from vector database.

    Args:
        index_ids_history: List of index IDs to delete
        vector_db_instance_id: UUID of the vector DB adapter instance
    """
    try:
        from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
            PromptIdeBaseTool,
        )

        organization_identifier = UserContext.get_organization_identifier()
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=organization_identifier)

        vector_db = VectorDB(
            tool=util,
            adapter_instance_id=vector_db_instance_id,
        )

        for index_id in index_ids_history:
            logger.debug(f"Deleting from VectorDB - index id: {index_id}")
            try:
                vector_db.delete(ref_doc_id=index_id)
            except Exception as e:
                # Log error and continue with the next index id
                logger.error(f"Error deleting index: {index_id} - {e}")

    except Exception as e:
        logger.error(f"Error in delete_from_vector_db: {e}", exc_info=True)


# Signal to perform vector DB cleanup on deletion
@receiver(pre_delete, sender=LookupIndexManager)
def perform_vector_db_cleanup(sender, instance, **kwargs):
    """Signal handler to clean up vector DB entries when index is deleted.

    This ensures that when a LookupIndexManager is deleted (e.g., when
    a data source is deleted or re-indexed), the corresponding vectors
    are removed from the vector database.
    """
    logger.debug(
        f"Performing vector DB cleanup for data source: "
        f"{instance.data_source.file_name}"
    )

    try:
        # Get the index_ids_history to clean up from the vector db
        index_ids_history = instance.index_ids_history

        if not index_ids_history:
            logger.debug("No index IDs to clean up")
            return

        if instance.profile_manager and instance.profile_manager.vector_store:
            vector_db_instance_id = str(instance.profile_manager.vector_store.id)
            delete_from_vector_db(index_ids_history, vector_db_instance_id)
        else:
            logger.warning(
                f"Cannot cleanup vector DB: missing profile or vector store "
                f"for data source {instance.data_source.file_name}"
            )

    except Exception as e:
        logger.warning(
            f"Error during vector DB cleanup for data source "
            f"{instance.data_source.file_name}: {e}",
            exc_info=True,
        )
