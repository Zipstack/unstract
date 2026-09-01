"""OpenAPI annotation for the ``whoami`` endpoint.

The serializers here shape the published spec only; they never parse a request
or build a response. They live outside ``serializers.py`` so that nothing at
request time imports one by accident, matching ``api_v2.openapi_schema``.

Their docstrings and help texts are published as the client-facing
descriptions, so they are written for the caller rather than the maintainer.

This operation does **not** reuse ``api_v2.openapi_schema.ErrorResponse``. That
shape comes from the project-wide exception handler, and nothing on this route
produces it. ``whoami`` is deliberately absent from ``WHITELISTED_PATHS``, so
``CustomAuthMiddleware`` answers almost every rejection itself, before DRF is
entered, with a bare ``{"message": ...}`` body. The one it does not reach --- a
caller who is authenticated but carries no platform key --- is answered by the
view in that same shape, deliberately, so one declaration covers both.
"""

from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from drf_standardized_errors.openapi import AutoSchema as StandardizedErrorsAutoSchema
from rest_framework import serializers

from platform_api.models import ApiKeyPermission


class PlatformKeyAutoSchema(StandardizedErrorsAutoSchema):
    """The project schema class, minus its error-body examples.

    ``drf_standardized_errors`` appends an example of the exception handler's
    ``{type, errors[]}`` body to every 4xx/5xx response, keyed on the status
    code alone and never on the declared serializer
    (``drf_standardized_errors/openapi.py:343-356``). On this operation the
    handler is never reached, so those examples contradict the ``$ref`` beside
    them -- a reader following the example writes ``errors[0].code`` and gets a
    ``KeyError`` on the wire.
    """

    def _get_error_response_examples(self) -> list:
        return []


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


class PlatformKeyError(serializers.Serializer):
    """Why a platform-key request was refused.

    Produced by the authentication middleware rather than by the project's
    exception handler, so it carries a single human-readable message and none
    of the per-field structure the organisation-scoped endpoints return.
    """

    message = serializers.CharField(help_text="Human-readable reason for the refusal.")


WHOAMI_DESCRIPTION = (
    "Resolve the organisation a platform API key belongs to.\n\n"
    "The organisation is read from the key itself, so this route carries no "
    "organisation segment and needs nothing but the key. Call it once and store "
    "`organization_id`; every other endpoint takes it as a path segment.\n\n"
    "Only a platform API key is accepted. An API deployment key authenticates "
    "against a different table on a path that never reaches this endpoint, and "
    "is rejected as unauthenticated.\n\n"
    "The same route also answers under an organisation segment "
    "(`/api/v1/unstract/{org}/whoami/`), where the key must additionally belong "
    "to the organisation named. Prefer the form documented here: it is the one "
    "that needs no organisation to begin with."
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
                PlatformKeyError,
                description="No usable platform API key was supplied — absent, "
                "malformed, unknown, or revoked.",
            ),
            403: OpenApiResponse(
                PlatformKeyError,
                description="The key was recognised but refused: its permission "
                "tier is not one this deployment knows, or the request named an "
                "organisation the key does not belong to.",
            ),
            500: OpenApiResponse(
                description="The request could not be served. The body is not "
                "guaranteed to be JSON.",
            ),
        },
        description=WHOAMI_DESCRIPTION,
    ),
)
