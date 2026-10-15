"""Role vocabulary, independent of any authentication provider.

Two role alphabets exist and both are wire contracts. Each value is stored in
``OrganizationMember.role`` and compared by the permission checks, so a
renamed value is a silent permission change.

- ``UserRole`` is the alphabet of the OSS default authentication service
  (``account_v2.authentication_service``), used when no authentication plugin
  is installed.
- ``UnstractRole`` is the alphabet of the authentication plugins (Auth0, Entra
  ID) and of the Zipstack ID ``roles`` claim. The SPA matches these strings
  literally (``RequireAuth.jsx``, ``RequireGuest.jsx``, ``SideNavBar.jsx``,
  ``TopNavBar.jsx``, ``InviteEditUser.jsx``, ``GetStaticData.js``).

The alphabets are disjoint: ``"admin"`` is an administrator only under the
default service, ``"unstract_admin"`` only under a plugin. Which one applies is
decided by the active authentication service's ``is_admin_by_role``.

Both are ``StrEnum``: a member compares equal to its stored string, so a call
site can hold the member instead of ``.value`` without changing a comparison.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Roles of the OSS default authentication service."""

    USER = "user"
    ADMIN = "admin"


class UnstractRole(StrEnum):
    """Roles of the authentication plugins, as stored and as sent to the SPA."""

    USER = "unstract_user"
    ADMIN = "unstract_admin"
    SUPERVISOR = "unstract_supervisor"
    REVIEWER = "unstract_reviewer"
    PLATFORM_ADMIN = "unstract_platform_admin"
