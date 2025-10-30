import uuid

from adapter_processor_v2.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class PlatformSettingsModelManager(DefaultOrganizationManagerMixin, models.Manager):
    """Manager for PlatformSettings model."""

    pass


class PlatformSettings(DefaultOrganizationMixin, BaseModel):
    """Platform-level settings for an organization.

    This model stores organization-wide settings including the system LLM
    adapter that will be used for platform operations like vibe extractor
    prompt generation.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Unique identifier for the platform settings",
    )

    # System LLM for platform operations (e.g., vibe extractor, prompt generation)
    system_llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_system_llm",
        db_comment="System LLM adapter used for platform-level AI operations like prompt generation",
    )

    objects = PlatformSettingsModelManager()

    class Meta:
        verbose_name = "Platform Setting"
        verbose_name_plural = "Platform Settings"
        db_table = "platform_settings"
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                name="unique_organization_platform_settings",
            ),
        ]

    def __str__(self) -> str:
        return f"PlatformSettings({self.organization})"

    @classmethod
    def get_for_organization(cls, organization):
        """Get or create platform settings for an organization.

        Args:
            organization: Organization instance

        Returns:
            PlatformSettings instance
        """
        settings, created = cls.objects.get_or_create(
            organization=organization,
            defaults={},
        )
        return settings
