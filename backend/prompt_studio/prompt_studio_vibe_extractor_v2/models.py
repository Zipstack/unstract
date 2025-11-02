import uuid

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel

from prompt_studio.prompt_studio_core_v2.models import CustomTool


class VibeExtractorProject(BaseModel):
    """Model to store Vibe Extractor project metadata.

    This stores the document type and tracks the generation process.
    All generated content (metadata.yaml, extraction.yaml, prompts)
    will be stored as files in the repository.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.TextField(
        blank=False,
        db_comment="Document type name (e.g., invoice, receipt)",
    )
    llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        related_name="vibe_extractor_projects_llm",
        null=True,
        blank=True,
        db_comment="LLM adapter used for generation (from platform system LLM)",
    )
    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.SET_NULL,
        related_name="vibe_extractor_projects",
        null=True,
        blank=True,
        db_comment="Associated custom tool",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="vibe_extractor_projects_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="vibe_extractor_projects_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Vibe Extractor Project"
        verbose_name_plural = "Vibe Extractor Projects"
        db_table = "vibe_extractor_project"
        indexes = [
            models.Index(fields=["document_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["tool_id"]),
        ]
