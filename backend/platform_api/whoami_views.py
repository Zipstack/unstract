"""Describe the platform API key a request is authenticated with.

A caller holding a key knows the secret but not what it is scoped to, and the
organisation identifier is otherwise only discoverable by reading it out of a
web-app URL. This endpoint answers "which organisation does this key belong
to?", so a client can resolve it once and store it.

The organisation is read off the key row, never off the URL: ``PlatformApiKey.key``
is unique, so a bearer token selects at most one row, and that row names its own
organisation. That is why this route carries no organisation segment.

``mcp_server.tools.platform.whoami`` answers the same question over MCP for the
same key. It predates this endpoint and spells the tier ``permission_tier``;
this one uses ``permission``, matching the model field. Adding a field to either
does not add it to the other.

The organisation fields are the trap in that pairing, not the tier. MCP's
``organization`` holds an **identifier**, not a display name
(``mcp_server/platform_views.py`` sets it from ``organization_id``), whereas
this endpoint splits the two into ``organization_id`` and ``organization_name``.
Aligning the two surfaces by field name would map ``organization`` onto
``organization_name`` and ship an id where a name is expected.
"""

from rest_framework import status, views
from rest_framework.request import Request
from rest_framework.response import Response

from platform_api.openapi_schema import WHOAMI_SCHEMA, PlatformKeyAutoSchema


@WHOAMI_SCHEMA
class WhoAmIView(views.APIView):
    """Report the organisation and scope of the calling platform API key."""

    # Authentication is CustomAuthMiddleware's job: it resolves the Bearer
    # token to a key row, binds the service account to request.user and
    # enforces the key's permission tier against the method. A permission
    # class here would only re-ask a question already answered.
    permission_classes: list = []

    # Narrows the standardized-errors example bodies to the statuses that
    # actually carry them. See PlatformKeyAutoSchema.
    schema = PlatformKeyAutoSchema()

    # authentication_classes is deliberately left alone. The project sets no
    # DEFAULT_AUTHENTICATION_CLASSES, so DRF's own default applies --
    # SessionAuthentication first -- and that is what carries the user
    # CustomAuthMiddleware bound into the view. Emptying this list would not
    # simplify anything and would drop that.
    def get(self, request: Request) -> Response:
        key = getattr(request, "platform_api_key", None)
        if key is None:
            # A session-authenticated browser user reaches this with no key to
            # describe. There is nothing to report, and reporting the session's
            # organisation instead would answer a question nobody asked.
            #
            # Returned rather than raised: DRF coerces NotAuthenticated to 403
            # unless the first authenticator offers a WWW-Authenticate header,
            # and SessionAuthentication offers none -- so a raise here would
            # answer 403 to a request whose problem is a missing credential.
            # The body matches what CustomAuthMiddleware sends for the same
            # class of failure. It does not cover every rejection this operation
            # publishes -- the declared 500 says its own body may not be JSON.
            #
            # WWW-Authenticate is required on a 401 by RFC 9110 s11.6.1, and
            # nothing upstream adds it: the middleware's own 401s omit it too.
            # Spelled as in mcp_server/transport.py, the one other place in the
            # codebase that emits it for this same credential.
            return Response(
                {"message": "This endpoint requires a platform API key."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": 'Bearer realm="platform"'},
            )

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
