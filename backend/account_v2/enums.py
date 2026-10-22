"""Role values, independent of any authentication provider.

Both alphabets are wire contracts: stored in ``OrganizationMember.role`` and
matched literally by the permission checks and the SPA, so renaming a value
silently changes permissions.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Roles of the OSS default authentication service (no auth plugin)."""

    USER = "user"
    ADMIN = "admin"


class UnstractRole(StrEnum):
    """Roles of the authentication plugins and of the Zipstack ID ``roles`` claim."""

    USER = "unstract_user"
    ADMIN = "unstract_admin"
    SUPERVISOR = "unstract_supervisor"
    REVIEWER = "unstract_reviewer"
    PLATFORM_ADMIN = "unstract_platform_admin"
