"""LookupProject model for Static Data-based Look-Ups."""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationMixin,
)

User = get_user_model()


class LookupProject(DefaultOrganizationMixin, BaseModel):
    """Represents a Look-Up project for static data-based enrichment.

    This model stores the configuration for a Look-Up project including
    LLM settings and organization association.
    """

    LOOKUP_TYPE_CHOICES = [
        ("static_data", "Static Data"),
    ]

    REFERENCE_DATA_TYPE_CHOICES = [
        ("vendor_catalog", "Vendor Catalog"),
        ("product_catalog", "Product Catalog"),
        ("customer_database", "Customer Database"),
        ("pricing_data", "Pricing Data"),
        ("compliance_rules", "Compliance Rules"),
        ("custom", "Custom"),
    ]

    LLM_PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("azure", "Azure OpenAI"),
        ("custom", "Custom Provider"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Name of the Look-Up project")
    description = models.TextField(
        blank=True, null=True, help_text="Description of the Look-Up project's purpose"
    )
    lookup_type = models.CharField(
        max_length=50,
        choices=LOOKUP_TYPE_CHOICES,
        default="static_data",
        help_text="Type of Look-Up (only static_data for POC)",
    )
    reference_data_type = models.CharField(
        max_length=50,
        choices=REFERENCE_DATA_TYPE_CHOICES,
        help_text="Category of reference data being stored",
    )

    # Template and status
    template = models.ForeignKey(
        "LookupPromptTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        help_text="Prompt template for this project",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this project is active"
    )
    metadata = models.JSONField(
        default=dict, blank=True, help_text="Additional metadata for the project"
    )

    # LLM Configuration
    llm_provider = models.CharField(
        max_length=50,
        choices=LLM_PROVIDER_CHOICES,
        null=True,
        blank=True,
        help_text="LLM provider to use for matching",
    )
    llm_model = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Specific model name (e.g., gpt-4-turbo, claude-3-opus)",
    )
    llm_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional LLM configuration (temperature, max_tokens, etc.)",
    )

    # Ownership
    created_by = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="created_lookup_projects",
        help_text="User who created this project",
    )

    # Note: created_at and modified_at are inherited from BaseModel
    # Note: organization ForeignKey is inherited from DefaultOrganizationMixin

    class Meta:
        """Model metadata."""

        db_table = "lookup_projects"
        ordering = ["-created_at"]
        verbose_name = "Look-Up Project"
        verbose_name_plural = "Look-Up Projects"
        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["modified_at"]),
        ]

    def __str__(self) -> str:
        """String representation of the project."""
        return self.name

    def get_absolute_url(self) -> str:
        """Get the URL for this project's detail view."""
        return reverse("lookup:project-detail", kwargs={"pk": self.pk})

    @property
    def is_ready(self) -> bool:
        """Check if the project has reference data ready for use.

        Returns:
            True if all reference data is extracted and ready, False otherwise.
        """
        if not hasattr(self, "data_sources"):
            return False

        latest_sources = self.data_sources.filter(is_latest=True)
        if not latest_sources.exists():
            return False

        return all(source.extraction_status == "completed" for source in latest_sources)

    def get_latest_reference_version(self) -> int | None:
        """Get the latest version number of reference data.

        Returns:
            Latest version number or None if no data sources exist.
        """
        if not hasattr(self, "data_sources"):
            return None

        latest = self.data_sources.filter(is_latest=True).first()
        return latest.version_number if latest else None

    def clean(self):
        """Validate model fields."""
        super().clean()
        from django.core.exceptions import ValidationError

        # Validate LLM provider
        valid_providers = [choice[0] for choice in self.LLM_PROVIDER_CHOICES]
        if self.llm_provider not in valid_providers:
            raise ValidationError(
                f"Invalid LLM provider: {self.llm_provider}. "
                f"Must be one of: {', '.join(valid_providers)}"
            )

        # Validate LLM config structure
        if self.llm_config and not isinstance(self.llm_config, dict):
            raise ValidationError("LLM config must be a dictionary")

        # Validate lookup_type (only static_data for POC)
        if self.lookup_type != "static_data":
            raise ValidationError(
                "Only 'static_data' lookup type is supported in this POC"
            )
