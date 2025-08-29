"""Constants for email notification system."""

from enum import Enum


class ResourceType(Enum):
    """Supported resource types for sharing notifications."""

    WORKFLOW = "workflow"
    TEXT_EXTRACTOR = "text_extractor"
    PROMPT_STUDIO = "text_extractor"  # Alias for backward compatibility


class EmailTemplateFields:
    """Standard template field names for SendGrid dynamic templates."""

    RESOURCE_TYPE = "resource_type"
    RESOURCE_NAME = "resource_name"
    RESOURCE_DESCRIPTION = "resource_description"
    SHARED_BY_NAME = "shared_by_name"
    SHARED_BY_EMAIL = "shared_by_email"
    RECIPIENT_NAME = "recipient_name"
    RECIPIENT_EMAIL = "recipient_email"
    ORGANIZATION_NAME = "organization_name"
    RESOURCE_URL = "resource_url"
    SHARED_DATE = "shared_date"
    ACTION_URL = "action_url"


class EmailTemplateDefaults:
    """Default values for email template fields."""

    RESOURCE_DESCRIPTIONS = {
        ResourceType.WORKFLOW.value: "A workflow that can be used for document processing and automation",
    }

    RESOURCE_TYPE_DISPLAY_NAMES = {
        ResourceType.WORKFLOW.value: "Workflow",
    }


class SharingEventType:
    """Types of sharing events."""

    RESOURCE_SHARED = "resource_shared"
    RESOURCE_ACCESS_REMOVED = "resource_access_removed"
    RESOURCE_PERMISSIONS_CHANGED = "resource_permissions_changed"
