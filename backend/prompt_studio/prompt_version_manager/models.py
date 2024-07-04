from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from utils.models.base_model import BaseModel


class PromptVersionManager(BaseModel):
    """Model class to store Prompt data for Custom Tool Studio.

    It has a many-to-one relation with CustomTool for ToolStudio.
    """

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
    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="prompt_version_tool_id",
        null=True,
        blank=True,
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
        if not self.pk:  # Only set version for new records
            max_version = PromptVersionManager.objects.filter(
                prompt_id=self.prompt_id
            ).aggregate(models.Max("version"))["version__max"]
            if max_version:
                next_version_number = (
                    int(max_version[1:]) + 1
                )  # Increment the version number
                self.version = f"v{next_version_number}"
            else:
                self.version = "v1"
        super().save(*args, **kwargs)

    class Meta:
        db_table = "prompt_version_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["tool_id", "prompt_id", "version"],
                name="unique_prompt_id_version",
            ),
        ]
