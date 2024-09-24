import logging

from notification.provider.webhook.webhook import Webhook

logger = logging.getLogger(__name__)


class SlackWebhook(Webhook):
    def send(self):
        """Send the Slack webhook notification."""
        formatted_payload = self.format_payload()
        self.payload = formatted_payload
        super().send()

    def get_headers(self):
        """Slack-specific headers."""
        headers = super().get_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def format_payload(self) -> dict:
        """Format the payload to match Slack's expected structure."""
        if "text" not in self.payload:
            # Construct a basic Slack message with 'text' field
            formatted_payload = {
                "text": "Notification",
                "blocks": self.create_blocks_from_payload(),
            }
        else:
            # If 'text' is already present, format accordingly
            formatted_payload = {
                "text": self.payload.pop("text"),
                "blocks": self.create_blocks_from_payload(),
            }
        return formatted_payload

    def create_blocks_from_payload(self) -> list:
        """Create Slack blocks from the given payload."""
        blocks = []
        # Header
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Unstract Update:*"},
            }
        )
        # Add a divider for separation
        blocks.append({"type": "divider"})
        # Add each key-value pair to the blocks
        for key, value in self.payload.items():
            formatted_key = key.replace("_", " ").title()
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{formatted_key}:* {value}"},
                }
            )
        # Footer
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*---*"}})
        return blocks
