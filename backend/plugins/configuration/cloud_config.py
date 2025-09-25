"""Cloud-specific configuration specs.

This module defines additional configuration keys that are only
available in cloud deployments. These extend the base OSS ConfigKey enum.
"""

from configuration.enums import ConfigSpec, ConfigType

try:
    from django.conf import settings
    # Try to access a setting to ensure Django is configured
    _ = settings.DEBUG
    django_configured = True
except:
    django_configured = False
    # Create a mock settings object for when Django isn't configured
    class settings:
        ENABLE_HIGHLIGHT_API_DEPLOYMENT = False


# Cloud-specific configuration specs
# These will be merged with base ConfigKey enum by the registry
config_specs = {
    "ENABLE_HIGHLIGHT_API_DEPLOYMENT": ConfigSpec(
        default=settings.ENABLE_HIGHLIGHT_API_DEPLOYMENT,
        value_type=ConfigType.BOOL,
        help_text="Enable highlight data for API deployments in standalone HITL",
    ),
    # Add more cloud-specific configs here as needed
}