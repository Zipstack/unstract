import uuid

from account_v2.models import User
from django.db import models
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from utils.models.base_model import BaseModel


class DocumentManager(BaseModel):
    """Model to store the document details."""

    document_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    document_name = models.CharField(
        db_comment="Field to store the document name",
        editable=False,
        null=False,
        blank=False,
    )

    tool = models.ForeignKey(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="document_managers",
        null=False,
        blank=False,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="document_managers_created",
        null=True,
        blank=True,
        editable=False,
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="document_managers_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Document Manager"
        verbose_name_plural = "Document Managers"
        db_table = "document_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["document_name", "tool"],
                name="unique_document_name_tool_index",
            ),
        ]
