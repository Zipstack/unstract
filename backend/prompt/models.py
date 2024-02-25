import uuid

from account.models import User
from django.db import models
from project.models import Project
from utils.models.base_model import BaseModel

VERSION_NAME_SIZE = 64
PROMPT_INPUT_SIZE = 1024


class Prompt(BaseModel):
    """Stores data related to a prompt created by a :model:`account.User` in an
    :model:`account.Org` for a :model:`project.Project`.

    Every org, project, version_name is assumed to be unique
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    version_name = models.CharField(max_length=VERSION_NAME_SIZE)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_prompts",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_prompts",
        null=True,
        blank=True,
    )
    prompt_input = models.CharField(max_length=PROMPT_INPUT_SIZE)
    promoted = models.BooleanField(default=False)
    # TODO: Replace once Workflow model is added
    # associated_workflow = models.ForeignKey(
    # "Workflow", on_delete=models.CASCADE)
    associated_workflow = models.IntegerField(null=True)

    def __str__(self) -> str:
        return f"Prompt({self.id}, input: {self.prompt_input}, \
            version: {self.version_name}, project: {self.project})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version_name"],
                name="unique_project_version",
            ),
        ]
