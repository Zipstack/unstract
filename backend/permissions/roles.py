from django.db import models


class ResourceRole(models.TextChoices):
    """Access role a user holds on a shared resource.

    ``OWNER`` ≈ creator / co-owner (full control); ``VIEWER`` ≈ shared user
    (read / use). A future ``EDITOR`` is a one-line addition here.
    """

    OWNER = "owner", "Owner"
    VIEWER = "viewer", "Viewer"
