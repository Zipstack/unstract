import uuid

from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)
from utils.user_context import UserContext


class TagModelManager(DefaultOrganizationManagerMixin, models.Manager):
    def get_or_create_tags(self, tag_names: list[str]) -> list["Tag"]:
        """
        Retrieves or creates tags based on a list of tag names.

        Args:
            tag_names (list): A list of tag names to retrieve or create.

        Returns:
            list: A list of Tag instances.
        """
        organization = UserContext.get_organization()
        if not organization:
            raise ValueError(
                "Organization context is required to retrieve or create tags."
            )

        tags: list[Tag] = []
        for tag_name in tag_names:
            tag, _ = self.get_or_create(
                name=tag_name,
                organization=organization,
                defaults={"description": f"Tag for {tag_name}"},
            )
            tags.append(tag)
        return tags


class Tag(DefaultOrganizationMixin, BaseModel):
    TAG_NAME_LENGTH = 50

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=TAG_NAME_LENGTH, db_comment="Unique name of the tag"
    )
    description = models.TextField(
        blank=True, null=True, db_comment="Description of the tag"
    )

    # Manager
    objects = TagModelManager()

    @classmethod
    def bulk_get_or_create(cls, tag_names: list[str]) -> list["Tag"]:
        """
        Class method to retrieve or create multiple tags for the current organization.

        Args:
            tag_names (list): A list of tag names to retrieve or create.

        Returns:
            list: A list of Tag instances associated with the current organization.
        """
        return cls.objects.get_or_create_tags(tag_names)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        db_table = "tag"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_tag_name_organization",
            ),
        ]
