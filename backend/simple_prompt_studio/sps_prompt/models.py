import uuid

from django.db import models
from simple_prompt_studio.sps_project.models import SPSProject
from utils.models.base_model import BaseModel


class SPSPrompt(BaseModel):
    prompt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_id = models.ForeignKey(
        SPSProject, on_delete=models.CASCADE, related_name="prompts"
    )
    prompt_key = models.CharField(
        db_comment="Field to store prompt key", max_length=255, editable=True
    )
    prompt = models.TextField(db_comment="Field to store prompt", editable=True)
    sequence_number = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "sps_prompt"
        constraints = [
            models.UniqueConstraint(
                fields=["tool_id", "prompt_key"], name="unique_prompt_key_per_project"
            )
        ]
