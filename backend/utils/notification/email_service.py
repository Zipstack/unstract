import logging
from typing import Any

from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails using SendGrid with dynamic templates."""

    def __init__(self) -> None:
        """Initialize SendGrid client with API key from settings."""
        self.api_key = settings.SENDGRID_API_KEY
        self.from_email = settings.SENDGRID_FROM_EMAIL
        self.from_name = settings.SENDGRID_FROM_NAME
        self.template_id = settings.SENDGRID_TEMPLATE_ID
        self.notifications_enabled = settings.ENABLE_EMAIL_NOTIFICATIONS
        self.client: SendGridAPIClient | None = None

        if self.api_key:
            self.client = SendGridAPIClient(api_key=self.api_key)

        self._validate_config()

    def _validate_config(self) -> bool:
        """Validate that all required SendGrid configuration is present."""
        if not self.notifications_enabled:
            logger.info("Email notifications are disabled")
            return False

        missing_config = []
        if not self.api_key:
            missing_config.append("SENDGRID_API_KEY")
        if not self.from_email:
            missing_config.append("SENDGRID_FROM_EMAIL")
        if not self.template_id:
            missing_config.append("SENDGRID_TEMPLATE_ID")

        if missing_config:
            missing_str = ", ".join(missing_config)
            logger.warning(f"Missing SendGrid configuration: {missing_str}")
            return False

        return True

    def send_template_email(
        self,
        recipients: list[str],
        template_data: dict[str, Any],
        template_id: str | None = None,
    ) -> bool:
        """Send an email using SendGrid dynamic template.

        Args:
            recipients: List of email addresses
            template_data: Dictionary of data to populate in the template
            template_id: Optional template ID override

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.notifications_enabled or not self._validate_config():
            logger.info("Email notifications disabled or misconfigured")
            return False

        if not recipients:
            logger.warning("No recipients provided for email")
            return False

        if not self.client:
            logger.error("SendGrid client not initialized")
            return False

        try:
            # Use provided template_id or fall back to default
            tid = template_id or self.template_id

            # Create personalization for each recipient
            personalizations = []
            for recipient in recipients:
                personalizations.append(
                    To(email=recipient, dynamic_template_data=template_data)
                )

            # Create Mail object
            message = Mail(
                from_email=(self.from_email, self.from_name), to_emails=personalizations
            )
            message.template_id = tid

            # Set dynamic subject if provided in template_data
            if "subject" in template_data:
                message.subject = template_data["subject"]

            # Send the email
            response = self.client.send(message)

            if response.status_code == 202:
                recipients_count = len(recipients)
                logger.info(
                    f"Email sent successfully to {recipients_count} recipients. "
                    f"SendGrid Response Headers: {dict(response.headers)}"
                )
                return True
            else:
                logger.error(
                    f"Failed to send email. Status: {response.status_code}, "
                    f"Body: {response.body}, Headers: {dict(response.headers)}"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

    def send_batch_emails(
        self, recipient_data_list: list[dict[str, Any]], template_id: str | None = None
    ) -> bool:
        """Send batch emails with personalized data for each recipient.

        Args:
            recipient_data_list: List of dictionaries containing
                                'email' and template data
            template_id: Optional template ID override

        Returns:
            bool: True if emails were sent successfully, False otherwise
        """
        if not self.notifications_enabled or not self._validate_config():
            return False

        if not recipient_data_list:
            logger.warning("No recipient data provided for batch email")
            return False

        if not self.client:
            logger.error("SendGrid client not initialized")
            return False

        try:
            tid = template_id or self.template_id

            # Create personalizations for batch sending
            personalizations = []
            for recipient_data in recipient_data_list:
                email = recipient_data.get("email")
                if not email:
                    logger.warning("Skipping recipient with missing email")
                    continue

                template_data = {k: v for k, v in recipient_data.items() if k != "email"}
                personalizations.append(
                    To(email=email, dynamic_template_data=template_data)
                )

            if not personalizations:
                logger.warning("No valid recipients found in batch data")
                return False

            # Create Mail object for batch sending
            message = Mail(
                from_email=(self.from_email, self.from_name), to_emails=personalizations
            )
            message.template_id = tid

            # Send the emails
            response = self.client.send(message)

            if response.status_code == 202:
                count = len(personalizations)
                logger.info(
                    f"Batch email sent successfully to {count} recipients. "
                    f"SendGrid Response Headers: {dict(response.headers)}"
                )
                return True
            else:
                status_code = response.status_code
                logger.error(
                    f"Failed to send batch email. Status: {status_code}, "
                    f"Body: {response.body}, Headers: {dict(response.headers)}"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending batch email: {str(e)}")
            return False

    def is_configured(self) -> bool:
        """Check if email service is properly configured and enabled."""
        return self.notifications_enabled and self._validate_config()


# Singleton instance
email_service = EmailService()
