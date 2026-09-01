"""Describe the platform API key a request is authenticated with.

A caller holding a key knows the secret but not what it is scoped to, and the
organisation identifier is otherwise only discoverable by reading it out of a
web-app URL. This endpoint answers "which organisation does this key belong
to?", so a client can resolve it once and store it.

The organisation is read off the key row, never off the URL: ``PlatformApiKey``
carries an ``organization`` FK stamped at mint time and a globally unique
``key``, so a bearer token maps to exactly one organisation by construction.
That is why this route carries no organisation segment.
"""

from rest_framework import status, views
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from platform_api.openapi_schema import WHOAMI_SCHEMA


@WHOAMI_SCHEMA
class WhoAmIView(views.APIView):
    """Report the organisation and scope of the calling platform API key."""

    # Authentication is CustomAuthMiddleware's job: it resolves the Bearer
    # token to a key row, binds the service account to request.user and
    # enforces the key's permission tier against the method. A permission
    # class here would only re-ask a question already answered.
    permission_classes: list = []

    # authentication_classes is deliberately not set. The project configures no
    # DEFAULT_AUTHENTICATION_CLASSES that resolves a user, so DRF's default
    # returns None and the middleware's request.user survives into the view.

    def get(self, request: Request) -> Response:
        key = getattr(request, "platform_api_key", None)
        if key is None:
            # A session-authenticated browser user reaches this with no key to
            # describe. There is nothing to report, and reporting the session's
            # organisation instead would answer a question nobody asked.
            raise NotAuthenticated("This endpoint requires a platform API key.")

        organization = key.organization
        return Response(
            {
                "organization_id": organization.organization_id,
                "organization_name": organization.display_name,
                "permission": key.permission,
                "key_name": key.name,
            },
            status=status.HTTP_200_OK,
        )
