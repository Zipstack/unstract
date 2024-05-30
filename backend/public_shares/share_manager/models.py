import uuid

from account.models import Organization, User
from django.db import models
from utils.models.base_model import BaseModel


class ShareManager(BaseModel):

    class ShareTypes(models.TextChoices):
        PROMPT_STUDIO = "PROMPT_STUDIO", "Publicly shared prompt studio project."

    share_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share_type = models.CharField(choices=ShareTypes.choices)
    organization_id = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="tool_org",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_shares",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_shares",
        null=True,
        blank=True,
    )
