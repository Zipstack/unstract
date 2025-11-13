"""Slack Webhook Notification Provider

This provider handles Slack-specific webhook notifications with proper
payload formatting for Slack's Block Kit API.
"""

from typing import Any

from notification.providers.webhook_provider import WebhookProvider
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class SlackWebhook(WebhookProvider):
    """Slack-specific webhook provider.

    Formats payloads according to Slack's expected structure,
    including support for Block Kit formatting.
    """

    def __init__(self):
        """Initialize Slack webhook provider."""
        super().__init__()
        self.provider_name = "SlackWebhook"

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare Slack-specific webhook data.

        Formats the payload to match Slack's expected structure
        with 'text' field and optional Block Kit blocks.

        Args:
            notification_data: Raw notification data

        Returns:
            Prepared notification data with Slack formatting
        """
        prepared_data = super().prepare_data(notification_data)

        # Format payload for Slack
        if "payload" in prepared_data:
            prepared_data["payload"] = self.format_payload(prepared_data["payload"])

        return prepared_data

    def format_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Format the payload to match Slack's expected structure.

        Args:
            payload: Original payload

        Returns:
            Slack-formatted payload with 'text' field and optional blocks
        """
        # If payload already has 'text' field, enhance it with blocks
        if "text" in payload:
            formatted_payload = {
                "text": payload.pop("text"),
                "blocks": self.create_blocks_from_payload(payload),
            }
        else:
            # Construct a Slack message from the payload
            formatted_payload = {
                "text": self._get_summary_text(payload),
                "blocks": self.create_blocks_from_payload(payload),
            }

        return formatted_payload

    def create_blocks_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Create Slack Block Kit blocks from the payload.

        Args:
            payload: Payload to convert to blocks

        Returns:
            List of Slack Block Kit blocks
        """
        blocks = []

        # Header block
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Unstract Notification*"},
            }
        )

        # Add divider for visual separation
        blocks.append({"type": "divider"})

        # Add each key-value pair as a section
        for key, value in payload.items():
            if value is None or value == "":
                continue

            # Format key for display
            formatted_key = self._format_key(key)

            # Format value based on type
            formatted_value = self._format_value(value)

            # Create section block with inline format
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{formatted_key}:* {formatted_value}",
                    },
                }
            )

        # Add timestamp footer if not already present
        if not any("timestamp" in str(block).lower() for block in blocks):
            from datetime import datetime

            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}_",
                        }
                    ],
                }
            )

        return blocks

    def _get_summary_text(self, payload: dict[str, Any]) -> str:
        """Generate summary text from payload.

        Args:
            payload: Payload to summarize

        Returns:
            Summary text for Slack notification
        """
        # Priority order for summary fields
        summary_fields = [
            "message",
            "status",
            "pipeline_name",
            "workflow_name",
            "api_name",
            "error",
            "result",
            "summary",
        ]

        for field in summary_fields:
            if field in payload and payload[field]:
                return str(payload[field])

        # Default summary
        return "Unstract Notification"

    def _format_key(self, key: str) -> str:
        """Format dictionary key for display.

        Args:
            key: Raw key name

        Returns:
            Formatted key for display
        """
        # Replace underscores with spaces and capitalize
        formatted = key.replace("_", " ").title()

        # Special formatting for known keys
        key_mapping = {
            "Pipeline Name": "Pipeline Name",
            "Api Name": "API Name",
            "Workflow Name": "Workflow Name",
            "Status": "Status",
            "Error": "Error",
            "Success": "Success",
            "Execution Id": "Execution Id",
            "Organization Id": "Organization Id",
        }

        return key_mapping.get(formatted, formatted)

    def _format_value(self, value: Any) -> str:
        """Format value for Slack display.

        Args:
            value: Value to format

        Returns:
            Formatted value string
        """
        if isinstance(value, bool):
            return "✅ Yes" if value else "❌ No"
        elif isinstance(value, (list, tuple)):
            return "\n• " + "\n• ".join(str(item) for item in value)
        elif isinstance(value, dict):
            # Format nested dictionary
            items = []
            for k, v in value.items():
                items.append(f"  • {self._format_key(k)}: {v}")
            return "\n" + "\n".join(items)
        elif value is None:
            return "_Not specified_"
        else:
            # Format long strings
            value_str = str(value)
            if len(value_str) > 500:
                return value_str[:497] + "..."
            return value_str

    def get_destination(self, notification_data: dict[str, Any]) -> str:
        """Extract webhook URL from notification data with masking for security."""
        url = notification_data.get("url", "unknown")

        # Mask sensitive webhook URLs for logging security
        if isinstance(url, str) and url != "unknown":
            if "hooks.slack.com" in url:
                # Mask Slack webhook tokens
                parts = url.split("/")
                if len(parts) >= 3:
                    return (
                        f"hooks.slack.com/services/{parts[-3][:4]}.../{parts[-2][:4]}..."
                    )
            elif len(url) > 50:
                # Mask long URLs that might contain tokens
                return url[:30] + "..." + url[-10:]

        return url
