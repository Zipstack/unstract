from abc import ABC, abstractmethod

from django.conf import settings
from notification_v2.models import Notification


class NotificationProvider(ABC):
    NOTIFICATION_TIMEOUT = settings.NOTIFICATION_TIMEOUT
    RETRY_DELAY = 10  # Seconds

    def __init__(self, notification: Notification, payload):
        self.payload = payload
        self.notification = notification

    @abstractmethod
    def send(self):
        """Method to be overridden in child classes for sending the
        notification."""
        raise NotImplementedError("Subclasses should implement this method.")

    def validate(self):
        """Method to validate the notification data."""
        pass

    @abstractmethod
    def get_headers(self):
        """Method to get the headers for the notification."""
        raise NotImplementedError("Subclasses should implement this method.")
