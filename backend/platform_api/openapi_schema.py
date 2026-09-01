"""OpenAPI annotation for the ``whoami`` endpoint.

The serializer here shapes the published spec only; it never parses a request
or builds a response. It lives outside ``serializers.py`` so that nothing at
request time imports it by accident, matching ``api_v2.openapi_schema``.

Its docstring and help texts are published as the client-facing descriptions,
so they are written for the caller rather than the maintainer.

The error body is imported rather than restated: it comes from the project-wide
exception handler, so it is the same shape for every endpoint in the spec.
"""

from api_v2.openapi_schema import ErrorResponse
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import serializers

from platform_api.models import ApiKeyPermission


class WhoAmIResponse(serializers.Serializer):
    """The organisation a platform API key belongs to, and what it may do."""

    organization_id = serializers.CharField(
        help_text="The organisation's identifier, as it appears in web-app URLs "
        "and in every organisation-scoped API path."
    )
    organization_name = serializers.CharField(
        help_text="The organisation's display name."
    )
    permission = serializers.ChoiceField(
        # Sourced from the model so a new tier cannot reach the API without
        # reaching the spec.
        choices=ApiKeyPermission.choices,
        help_text="The key's permission tier, which decides the HTTP methods it "
        "may issue.",
    )
    key_name = serializers.CharField(help_text="The key's name, as it was minted.")


WHOAMI_DESCRIPTION = (
    "Resolve the organisation a platform API key belongs to.\n\n"
    "The organisation is read from the key itself, so this route carries no "
    "organisation segment and needs nothing but the key. Call it once and store "
    "`organization_id`; every other endpoint takes it as a path segment.\n\n"
    "Only a platform API key is accepted. An API deployment key authenticates "
    "against a different table on a path that never reaches this endpoint, and "
    "is rejected as unauthenticated."
)


# Generated clients take their method names and module paths from here, so this
# is part of the public API surface.
WHOAMI_SCHEMA = extend_schema_view(
    get=extend_schema(
        operation_id="whoami",
        tags=["identity"],
        auth=[{"platformKey": []}],
        responses={
            200: WhoAmIResponse,
            401: OpenApiResponse(
                ErrorResponse,
                description="No usable platform API key was supplied.",
            ),
            403: OpenApiResponse(
                ErrorResponse,
                description="The key is not permitted to issue this request.",
            ),
            500: OpenApiResponse(
                ErrorResponse,
                description="The organisation could not be resolved.",
            ),
        },
        description=WHOAMI_DESCRIPTION,
    ),
)
