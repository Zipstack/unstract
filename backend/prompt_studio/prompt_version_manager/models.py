import uuid

from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from utils.models.base_model import BaseModel


class PromptVersionManager(BaseModel):
    """Model class to store Prompt data for Custom Tool Studio."""

    class EnforceType(models.TextChoices):
        TEXT = "Text", "Response sent as Text"
        NUMBER = "number", "Response sent as number"
        EMAIL = "email", "Response sent as email"
        DATE = "date", "Response sent as date"
        BOOLEAN = "boolean", "Response sent as boolean"
        JSON = "json", "Response sent as json"

    class PromptType(models.TextChoices):
        PROMPT = "PROMPT", "Response sent as Text"
        NOTES = "NOTES", "Response sent as float"

    class Mode(models.TextChoices):
        DEFAULT = "Default", "Default choice for output"

    prompt_version_manager_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Field to store the UUID for the tag manager helper",
    )
    prompt_id = models.ForeignKey(
        ToolStudioPrompt, on_delete=models.CASCADE, editable=False
    )
    prompt_key = models.TextField(
        blank=False,
        db_comment="Field to store the prompt key",
    )
    enforce_type = models.TextField(
        blank=False,
        db_comment="Field to store the type in which the response to be returned.",
        choices=EnforceType.choices,
        default=EnforceType.TEXT,
    )
    prompt = models.TextField(
        blank=True, db_comment="Field to store the prompt", unique=False
    )
    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="prompt_version_profile_manager",
        null=True,
        blank=True,
    )
    version = models.CharField(max_length=10)

    def save(self, *args, **kwargs):
        self.version = self.calculate_next_version(self.prompt_id)
        super().save(*args, **kwargs)

    @staticmethod
    def calculate_next_version(prompt_id):
        previous_version = PromptVersionManager.objects.filter(
            prompt_id=prompt_id
        ).aggregate(models.Max("version"))["version__max"]
        if previous_version:
            next_version_number = int(previous_version[1:]) + 1
            return f"v{next_version_number}"
        else:
            return "v1"

    class Meta:
        db_table = "prompt_version_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["prompt_id", "version"],
                name="unique_prompt_id_version",
            ),
            models.UniqueConstraint(
                fields=[
                    "prompt_id",
                    "prompt_key",
                    "enforce_type",
                    "prompt",
                    "profile_manager",
                ],
                name="unique_prompt_fields",
            ),
        ]
