"""Validation Utilities

Input validation functions for workers.
"""

import os
import re

from ..constants import SecurityConfig


def validate_execution_id(execution_id: str) -> bool:
    """Validate execution ID format."""
    return bool(re.match(SecurityConfig.VALID_UUID_PATTERN, execution_id))


def validate_organization_id(org_id: str) -> bool:
    """Validate organization ID format."""
    return bool(re.match(SecurityConfig.VALID_ORGANIZATION_ID_PATTERN, org_id))


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    # Limit length
    if len(sanitized) > SecurityConfig.MAX_FILE_NAME_LENGTH:
        name, ext = os.path.splitext(sanitized)
        max_name_length = SecurityConfig.MAX_FILE_NAME_LENGTH - len(ext)
        sanitized = name[:max_name_length] + ext
    return sanitized
