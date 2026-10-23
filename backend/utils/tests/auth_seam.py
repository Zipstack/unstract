"""Reach the authentication seam the way production code does.

A distribution can install an auth plugin that replaces the built-in
``AuthenticationService`` (cloud installs Auth0). The plugin names roles its own
way and makes its own identity-provider calls. A test that hardcodes the
built-in behaviour -- a ``role="admin"`` row, a patch on
``AuthenticationService`` -- passes here and fails under the plugin, or passes
there without exercising it.

So ask the active service instead of assuming the answer: build membership rows
with :func:`admin_role` / :func:`member_role`, and stub identity-provider calls
with :func:`patch_auth_service`. One test then checks the feature under every
distribution. Only a test whose subject *is* the built-in service pins it, with
:func:`builtin_auth_service`.
"""

from typing import Any
from unittest.mock import patch

from account_v2.authentication_controller import AuthenticationController
from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.enums import UnstractRole, UserRole


def active_auth_service() -> Any:
    """The auth service production code would use: the plugin's, else built-in."""
    return AuthenticationController().auth_service


def admin_role() -> str:
    """The role name the active auth service treats as organisation admin."""
    return _role_names()[0]


def member_role() -> str:
    """The role name of an ordinary, non-admin organisation member."""
    return _role_names()[1]


def patch_auth_service(attribute: str, **kwargs: Any) -> Any:
    """``patch.object`` on the active auth service's class.

    Patches the class, not one instance: ``AuthenticationController`` builds a
    fresh service per request, and a patch on ``AuthenticationService`` misses
    when a plugin's class is the one in use. Use it for identity-provider calls
    (``invite_user``, ``user_organizations``, ...) -- the boundary a unit test
    should not cross -- and let the role logic run for real.
    """
    return patch.object(type(active_auth_service()), attribute, **kwargs)


def builtin_auth_service() -> Any:
    """Run on the built-in ``AuthenticationService`` whatever plugin is installed.

    Under a plugin this turns the plugin off, so the test no longer checks the
    distribution it runs in. Use it only when the built-in service is the
    subject, and say in a comment why and where the plugin's own behaviour is
    tested. In a ``TestCase``: ``self.enterContext(builtin_auth_service())``.
    """
    return patch.object(
        AuthenticationPluginRegistry, "is_plugin_available", return_value=False
    )


def _role_names() -> tuple[str, str]:
    service = active_auth_service()
    # The built-in service speaks UserRole; the plugins speak UnstractRole.
    for roles in (UserRole, UnstractRole):
        if service.is_admin_by_role(roles.ADMIN) and not service.is_admin_by_role(
            roles.USER
        ):
            return roles.ADMIN.value, roles.USER.value
    raise AssertionError(
        f"{type(service).__name__} treats neither {UserRole.ADMIN!r} nor "
        f"{UnstractRole.ADMIN!r} as admin; teach utils.tests.auth_seam its roles."
    )
