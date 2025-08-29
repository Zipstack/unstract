"""Helper functions for sending resource sharing notifications via email."""

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from account_v2.models import User
from django.conf import settings

from utils.models.organization_mixin import DefaultOrganizationMixin

from .constants import (
    EmailTemplateDefaults,
    EmailTemplateFields,
    ResourceType,
    SharingEventType,
)
from .email_service import email_service
from .exceptions import InvalidRecipientError, TemplateDataError

logger = logging.getLogger(__name__)


class SharingNotificationService:
    """Service for sending resource sharing notifications."""

    def __init__(self):
        """Initialize the notification service."""
        self.email_service = email_service

    def send_sharing_notification(
        self,
        resource_type: str,
        resource_name: str,
        resource_id: str,
        shared_by: User,
        shared_to: list[User],
        resource_instance: DefaultOrganizationMixin | None = None,
        event_type: str = SharingEventType.RESOURCE_SHARED,
    ) -> bool:
        """Send sharing notification emails to newly shared users.

        Args:
            resource_type: Type of resource (workflow, text_extractor)
            resource_name: Display name of the resource
            resource_id: ID of the shared resource
            shared_by: User who is sharing the resource
            shared_to: List of users to notify about sharing
            resource_instance: Optional resource instance for additional data
            event_type: Type of sharing event

        Returns:
            bool: True if notification was sent successfully
        """
        if not self.email_service.is_configured():
            logger.info("Email service not configured, skipping notification")
            return False

        if not shared_to:
            logger.info("No users to notify about sharing")
            return True

        try:
            # Validate inputs
            self._validate_inputs(resource_type, resource_name, shared_by, shared_to)

            # Build template data
            template_data = self._build_template_data(
                resource_type=resource_type,
                resource_name=resource_name,
                resource_id=resource_id,
                shared_by=shared_by,
                resource_instance=resource_instance,
                event_type=event_type,
            )

            # Prepare recipient data for batch sending
            recipient_data_list = []
            for user in shared_to:
                if not user.email:
                    logger.warning(f"User {user.id} has no email, skipping")
                    continue

                # Create personalized data for each recipient
                personalized_data = template_data.copy()
                personalized_data.update(
                    {
                        EmailTemplateFields.RECIPIENT_NAME: self._get_user_name(user),
                        EmailTemplateFields.RECIPIENT_EMAIL: user.email,
                    }
                )

                recipient_data_list.append({"email": user.email, **personalized_data})

            if not recipient_data_list:
                logger.warning("No valid recipients with email addresses")
                return False

            # Debug log the template data being sent
            logger.debug(f"Sending email with template data: {recipient_data_list}")

            # Send batch emails
            success = self.email_service.send_batch_emails(recipient_data_list)

            if success:
                recipient_count = len(recipient_data_list)
                logger.info(
                    f"Sharing notification sent to {recipient_count} users "
                    f"for {resource_type}: {resource_name}"
                )

            return success

        except Exception as e:
            logger.error(f"Error sending sharing notification: {str(e)}")
            return False

    def _validate_inputs(
        self,
        resource_type: str,
        resource_name: str,
        shared_by: User,
        shared_to: list[User],
    ) -> None:
        """Validate input parameters."""
        if not resource_type or resource_type not in [rt.value for rt in ResourceType]:
            raise TemplateDataError(f"Invalid resource type: {resource_type}")

        if not resource_name:
            raise TemplateDataError("Resource name is required")

        if not shared_by or not shared_by.email:
            raise InvalidRecipientError("Shared by user must have valid email")

        if not shared_to:
            raise InvalidRecipientError("At least one recipient is required")

    def _build_template_data(
        self,
        resource_type: str,
        resource_name: str,
        resource_id: str,
        shared_by: User,
        resource_instance: DefaultOrganizationMixin | None = None,
        event_type: str = SharingEventType.RESOURCE_SHARED,
    ) -> dict[str, Any]:
        """Build template data for SendGrid dynamic template."""
        # Get resource type display name
        display_name = EmailTemplateDefaults.RESOURCE_TYPE_DISPLAY_NAMES.get(
            resource_type, resource_type.title()
        )

        # Get resource description
        description = EmailTemplateDefaults.RESOURCE_DESCRIPTIONS.get(
            resource_type, f"A {resource_type} resource"
        )

        # Get organization name and ID
        organization_name = "Your Organization"
        organization_id = None
        if resource_instance and hasattr(resource_instance, "organization"):
            org = resource_instance.organization
            if org:
                organization_id = org.name

        # Build resource URL with organization ID
        resource_url = self._build_resource_url(
            resource_type, resource_id, organization_id
        )

        # Build template data
        template_data = {
            EmailTemplateFields.RESOURCE_TYPE: display_name,
            EmailTemplateFields.RESOURCE_NAME: resource_name,
            EmailTemplateFields.RESOURCE_DESCRIPTION: description,
            EmailTemplateFields.SHARED_BY_NAME: self._get_user_name(shared_by),
            EmailTemplateFields.SHARED_BY_EMAIL: shared_by.email,
            EmailTemplateFields.ORGANIZATION_NAME: organization_name,
            EmailTemplateFields.RESOURCE_URL: resource_url,
            EmailTemplateFields.ACTION_URL: resource_url,
            EmailTemplateFields.SHARED_DATE: datetime.now().strftime(
                "%B %d, %Y at %I:%M %p"
            ),
            # Add subject for the email
            "subject": f'{display_name} "{resource_name}" has been shared with you',
        }

        return template_data

    def _build_resource_url(
        self, resource_type: str, resource_id: str, organization_id: str | None = None
    ) -> str:
        """Build URL to access the shared resource."""
        # Base URL from settings or default
        base_url = getattr(settings, "WEB_APP_ORIGIN_URL", "http://localhost:3000")

        # If no organization ID provided, try to get from context
        if not organization_id:
            from utils.user_context import UserContext

            org = UserContext.get_organization()
            if org:
                organization_id = org.name

        if not organization_id:
            # Fallback to simple URL without org ID
            logger.warning("Organization ID not available for URL building")
            resource_path = f"/{resource_type}/{resource_id}"
        else:
            # Build URL with organization ID
            # Pattern: /<org_id>/workflows/<workflow_id>
            path_mapping = {
                ResourceType.WORKFLOW.value: (
                    f"/{organization_id}/workflows/{resource_id}"
                ),
            }
            resource_path = path_mapping.get(
                resource_type, f"/{organization_id}/{resource_type}/{resource_id}"
            )

        return urljoin(base_url, resource_path)

    def _get_user_name(self, user: User) -> str:
        """Get display name for a user."""
        if hasattr(user, "get_full_name") and user.get_full_name():
            return user.get_full_name()
        elif hasattr(user, "username") and user.username:
            return user.username
        elif user.email:
            return user.email.split("@")[0]
        else:
            return f"User {user.id}"

    def send_access_removed_notification(
        self,
        resource_type: str,
        resource_name: str,
        removed_from: list[User],
        removed_by: User,
    ) -> bool:
        """Send notification when users' access is removed from a resource.

        Args:
            resource_type: Type of resource
            resource_name: Name of the resource
            removed_from: List of users whose access was removed
            removed_by: User who removed the access

        Returns:
            bool: True if notification was sent successfully
        """
        # This method can be implemented later when needed
        logger.info(
            f"Access removal notification not implemented yet for "
            f"{resource_type}: {resource_name}"
        )
        return True


# Singleton instance
sharing_notification_service = SharingNotificationService()
