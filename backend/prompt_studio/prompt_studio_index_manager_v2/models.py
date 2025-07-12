import json
import logging
import uuid

from account_v2.models import User
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import PromptIdeBaseTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from utils.models.base_model import BaseModel
from utils.user_context import UserContext

from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import LogLevel
    from unstract.sdk1.vector_db import VectorDB
else:
    from unstract.sdk.constants import LogLevel
    from unstract.sdk.vector_db import VectorDB

logger = logging.getLogger(__name__)


class IndexManager(BaseModel):
    """Model to store the index details."""

    index_manager_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    document_manager = models.ForeignKey(
        DocumentManager,
        on_delete=models.CASCADE,
        related_name="index_managers",
        editable=False,
        null=False,
        blank=False,
    )

    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="index_managers",
        editable=False,
        null=True,
        blank=True,
    )

    raw_index_id = models.CharField(
        db_comment="Field to store the raw index id",
        editable=False,
        null=True,
        blank=True,
    )

    summarize_index_id = models.CharField(
        db_comment="Field to store the summarize index id",
        editable=False,
        null=True,
        blank=True,
    )

    index_ids_history = models.JSONField(
        db_comment="List of index ids",
        default=list,
        null=False,
        blank=False,
    )
    extraction_status = models.JSONField(
        db_comment="Extraction status for documents",
        null=False,
        blank=False,
        default=dict,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="index_managers_created",
        null=True,
        blank=True,
        editable=False,
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="index_managers_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Index Manager"
        verbose_name_plural = "Index Managers"
        db_table = "index_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["document_manager", "profile_manager"],
                name="unique_document_manager_profile_manager_index",
            ),
        ]


def delete_from_vector_db(index_ids_history, vector_db_instance_id):
    organization_identifier = UserContext.get_organization_identifier()
    util = PromptIdeBaseTool(
        log_level=LogLevel.INFO,
        org_id=organization_identifier
    )
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


# Function will be executed every time an instance of IndexManager is deleted.
@receiver(pre_delete, sender=IndexManager)
def perform_vector_db_cleanup(sender, instance, **kwargs):
    """Signal to perform vector db cleanup."""
    logger.debug(
        "Performing vector db cleanup for Document tool id: "
        f"{instance.document_manager.tool_id}"
    )
    try:
        # Get the index_ids_history to clean up from the vector db
        index_ids_history = json.loads(instance.index_ids_history)
        vector_db_instance_id = str(instance.profile_manager.vector_store.id)
        delete_from_vector_db(index_ids_history, vector_db_instance_id)
    except Exception as e:
        logger.warning(
            "Error during vector DB cleanup for deleted document "
            "in prompt studio tool %s: %s",
            instance.document_manager.tool_id,
            e,
            exc_info=True,  # For additional stack trace
        )
