import json
import logging
import uuid

from account.models import User
from django.db import connection, models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio_core.prompt_ide_base_tool import PromptIdeBaseTool
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from unstract.sdk.constants import LogLevel
from unstract.sdk.embedding import Embedding
from unstract.sdk.exceptions import SdkError
from unstract.sdk.vector_db import VectorDB
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel

logger = logging.getLogger(__name__)


class IndexManager(BaseModel):
    """Model to store the index details."""

    index_manager_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    document_manager = models.ForeignKey(
        DocumentManager,
        on_delete=models.CASCADE,
        related_name="index_manager_linked_document",
        editable=False,
        null=False,
        blank=False,
    )

    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="index_manager_linked_raw_llm_profile",
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

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_index_manager_created_by",
        null=True,
        blank=True,
        editable=False,
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_index_manager_modified_by",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_manager", "profile_manager"],
                name="unique_document_manager_profile_manager",
            ),
        ]


# Function will be executed every time an instance of IndexManager is deleted.
@receiver(post_delete, sender=IndexManager)
def perform_vector_db_cleanup(sender, instance, **kwargs):
    """Signal to perform vector db cleanup."""
    logger.info("Performing vector db cleanup")
    # Get the index_ids_history to clean up from the vector db
    index_ids_history = json.loads(instance.index_ids_history)
    embedding_instance_id = str(instance.profile_manager.embedding_model.id)
    vector_db_instance_id = str(instance.profile_manager.vector_store.id)
    # Generate a run_id
    run_id = CommonUtils.get_uuid()
    usage_kwargs = {"run_id": run_id}
    org_schema = connection.tenant.schema_name
    util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_schema)
    try:
        embedding = Embedding(
            tool=util,
            adapter_instance_id=embedding_instance_id,
            usage_kwargs=usage_kwargs,
        )

        vector_db = VectorDB(
            tool=util,
            adapter_instance_id=vector_db_instance_id,
            embedding=embedding,
        )
        for index_id in index_ids_history:
            logger.info(f"Deleting index_id: {index_id}")
            vector_db.delete(ref_doc_id=index_id)
    # Not raising any exception.
    # Cleanup should not fail the deletion of the index manager.
    except SdkError as e:
        logger.error(f"Error while performing vector db cleanup: {e}")
        return
