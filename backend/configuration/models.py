import logging
import uuid
from typing import Any

from account_v2.models import Organization
from django.core.exceptions import ValidationError
from django.db import models
from utils.models.base_model import BaseModel

from configuration.config_registry import ConfigurationRegistry
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
        """Validate that the key field contains a valid configuration key."""
        super().clean()
        if self.key and not ConfigurationRegistry.is_config_key_available(self.key):
            available_keys = list(ConfigurationRegistry.get_all_config_keys().keys())
            raise ValidationError(
                {
                    "key": f"Invalid configuration key '{self.key}'. Must be one of: {available_keys}"
                }
            )

    @property
    def typed_value(self) -> Any:
        """Convert stored string value to proper type based on configuration specification."""
        try:
            return ConfigurationRegistry.cast_value(self.key, self.value)
        except (ValueError, KeyError, TypeError):
            return None

    @classmethod
    def get_value_by_organization(
        cls, config_key: ConfigKey | str, organization: Organization | None = None
    ) -> Any:
        """Get configuration value for an organization with proper fallback to defaults.

        This method handles all error cases and returns the appropriate default value:
        - If no organization provided: returns config default
        - If configuration not found: returns config default
        - If configuration disabled: returns config default
        - If value casting fails: returns config default
        - If value is invalid (e.g., 0, negative): returns config default

        Args:
            config_key: The configuration key (ConfigKey enum or string name) to retrieve
            organization: The organization to get config for, None for default

        Returns:
            The typed configuration value or default if not found/invalid
        """
        # Handle both ConfigKey enum and string key names
        if isinstance(config_key, ConfigKey):
            key_name = config_key.name
        else:
            key_name = config_key

        # Get the config spec from registry
        config_spec = ConfigurationRegistry.get_config_spec(key_name)
        if not config_spec:
            logger.error(f"Configuration key '{key_name}' not found in registry")
            raise ValueError(f"Unknown configuration key: {key_name}")

        default_value = config_spec.default

        if not organization:
            return default_value

        try:
            config = cls.objects.get(organization=organization, key=key_name)
            if not config.enabled:
                return default_value

            # Get the typed value, which includes validation
            typed_value = config.typed_value

            # Additional safety check - if typed_value is None, return default
            if typed_value is None:
                logger.warning(
                    f"Configuration {key_name} for organization {organization.id} "
                    f"returned None, using default value {default_value}"
                )
                return default_value

            return typed_value

        except cls.DoesNotExist:
            return default_value
        except Exception as e:
            logger.warning(
                f"Configuration {key_name} for organization {organization.id if organization else 'None'} "
                f"has invalid value, using default {default_value}. Error: {e}"
            )
            return default_value
