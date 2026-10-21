from enum import Enum

from django.db import models


class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"


class Product(models.TextChoices):
    """Product ids a user can land in.

    ``verticals`` is API Hub, the key the v0 product switcher already stores.
    ``flow`` has no product in these repositories yet; where it lands is
    configuration on the client, so storing it needs nothing here.
    """

    UNSTRACT = "unstract", "Unstract"
    LLM_WHISPERER = "llm-whisperer", "LLMWhisperer"
    VERTICALS = "verticals", "API Hub"
    FLOW = "flow", "Flow"
