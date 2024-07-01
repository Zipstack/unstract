import uuid

from django.db import models
from utils.models.base_model import BaseModel
from simple_prompt_studio.sps_prompt.models import SPSPrompt
from simple_prompt_studio.sps_document.models import SPSDocument
from simple_prompt_studio.sps_project.models import SPSProject

class SPSPromptOutput(BaseModel):
    prompt_output_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    output = models.CharField(
        db_comment="Field to store output", editable=True, null=True, blank=True
    )
    prompt_id = models.ForeignKey(
        SPSPrompt,
        on_delete=models.CASCADE,
        related_name="prompt_outputs",
    )
    document_manager = models.ForeignKey(
        SPSDocument,
        on_delete=models.CASCADE,
        related_name="prompt_outputs",
    )
    tool_id = models.ForeignKey(
        SPSProject,
        on_delete=models.CASCADE,
        related_name="prompt_outputs",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "prompt_id",
                    "document_manager",
                    "tool_id",
                ],
                name="unique_sps_prompt_output",
            ),
        ]