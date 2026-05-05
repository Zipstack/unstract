from enum import Enum


class NotificationType(Enum):
    WEBHOOK = "WEBHOOK"
    # Add other notification types as needed
    # Example EMAIL = 'EMAIL'

    def get_valid_platforms(self):
        if self == NotificationType.WEBHOOK:
            return [PlatformType.SLACK.value, PlatformType.API.value]
        return []

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class AuthorizationType(Enum):
    BEARER = "BEARER"
    API_KEY = "API_KEY"
    CUSTOM_HEADER = "CUSTOM_HEADER"
    NONE = "NONE"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class PlatformType(Enum):
    SLACK = "SLACK"
    API = "API"
    # Add other platforms as needed
    # Example TEAMS = 'TEAMS'

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]
