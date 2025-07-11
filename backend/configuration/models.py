import logging
import uuid
from typing import Any

from account_v2.models import Organization
from django.core.exceptions import ValidationError
from django.db import models
from utils.models.base_model import BaseModel

from configuration.enums import ConfigKey

logger = logging.getLogger(__name__)


class Configuration(BaseModel):
    """Model to hold details of Organization configs.

    This model stores internal system configuration overrides at the organization level.
    These configurations are NOT user-facing and should not be exposed through user APIs.
    They are meant to override environment variables for different organizations.

    Note: This is kept separate from platform_settings_v2 module because:
    - platform_settings_v2: User-facing API key management
    - configuration: Internal system configuration (hidden from users)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="organization_configuration"
    )
    key = models.CharField(
        max_length=100,
        help_text="Configuration key - must be a valid ConfigKey enum value",
    )
    value = models.TextField()
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"
        db_table = "configuration"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"],
                name="unique_organization_key",
            ),
        ]

    def clean(self):
        """Validate that the key field contains a valid ConfigKey enum value."""
        super().clean()
        if self.key and self.key not in [config.name for config in ConfigKey]:
            raise ValidationError(
                {
                    "key": f"Invalid configuration key '{self.key}'. Must be one of: {[config.name for config in ConfigKey]}"
                }
            )

    @property
    def typed_value(self) -> Any:
        """Convert stored string value to proper type based on ConfigKey specification."""
        try:
            spec = ConfigKey[self.key].cast_value(self.value)
            return spec
        except (ValueError, KeyError, TypeError):
            return None

    @classmethod
    def get_value_by_organization(
        cls, config_key: ConfigKey, organization: Organization | None = None
    ) -> Any:
        """Get configuration value for an organization with proper fallback to defaults.

        This method handles all error cases and returns the appropriate default value:
        - If no organization provided: returns ConfigKey default
        - If configuration not found: returns ConfigKey default
        - If configuration disabled: returns ConfigKey default
        - If value casting fails: returns ConfigKey default
        - If value is invalid (e.g., 0, negative): returns ConfigKey default

        Args:
            config_key: The configuration key enum to retrieve
            organization: The organization to get config for, None for default

        Returns:
            The typed configuration value or default if not found/invalid
        """
        if not organization:
            return config_key.value.default

        try:
            config = cls.objects.get(organization=organization, key=config_key.name)
            if not config.enabled:
                return config_key.value.default

            # Get the typed value, which includes validation
            typed_value = config.typed_value

            # Additional safety check - if typed_value is None, return default
            if typed_value is None:
                logger.warning(
                    f"Configuration {config_key.name} for organization {organization.id} "
                    f"returned None, using default value {config_key.value.default}"
                )
                return config_key.value.default

            return typed_value

        except cls.DoesNotExist:
            return config_key.value.default
        except Exception as e:
            logger.warning(
                f"Configuration {config_key.name} for organization {organization.id if organization else 'None'} "
                f"has invalid value, using default {config_key.value.default}. Error: {e}"
            )
            return config_key.value.default
