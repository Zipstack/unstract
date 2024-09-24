from notification.provider.webhook.webhook import Webhook


class APIWebhook(Webhook):
    def send(self):
        """Send the API webhook notification."""
        super().send()

    def get_headers(self):
        """API-specific headers."""
        headers = super().get_headers()
        headers["Content-Type"] = "application/json"
        return headers
