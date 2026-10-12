"""Parse a request-supplied id as a UUID, or fail as a 400.

These columns are UUID primary/foreign keys, so a non-UUID value makes
``filter()`` raise Django's ``ValidationError`` while the query is being
*built*. drf_standardized_errors maps only ``Http404`` and Django's
``PermissionDenied``, so that surfaced as a 500 rather than a 400.

Shared rather than copied per view: this is a security-relevant parse, and two
copies are two chances for one of them to widen its except tuple or lose a case.
"""

import uuid
from typing import Any

from rest_framework.exceptions import ValidationError


def validated_uuid(raw: Any, field_name: str) -> uuid.UUID:
    """``raw`` as a UUID, or a 400 naming ``field_name``."""
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(detail=f"'{field_name}' must be a valid UUID.")
