import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.org_aware_manager import OrgAwareManager

from prompt_studio.prompt_studio_core_v2.models import CustomTool


class DocumentManager(BaseModel):
    """Model to store the document details."""

    # Org scoping lives at the manager because OrganizationFilterBackend only
    # scopes querysets routed through filter_queryset(). A raw Model.objects
    # lookup inside a view bypasses it — including inside a custom @action,
    # whose own self.get_object() *is* filtered but whose hand-written queries
    # are not.
    objects = OrgAwareManager()

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
