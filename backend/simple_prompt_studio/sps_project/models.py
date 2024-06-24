import uuid

from django.db import models
from utils.models.base_model import BaseModel


class SPSProject(BaseModel):
    tool_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_name = models.TextField(
        blank=True,
        db_comment="Field to store the name of the Simple Prompt Studio Project.",
    )

    class Meta:
        db_table = "sps_project"
