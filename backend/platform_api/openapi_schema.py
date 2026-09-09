"""OpenAPI annotation for the ``whoami`` endpoint.

The serializers here shape the published spec only; they never parse a request
or build a response. They live outside ``serializers.py`` so that nothing at
request time imports one by accident, matching ``api_v2.openapi_schema``.

Their docstrings and help texts are published as the client-facing
descriptions, so they are written for the caller rather than the maintainer.

This operation publishes **one** error shape. ``whoami`` is deliberately absent
from ``WHITELISTED_PATHS``, so ``CustomAuthMiddleware`` authenticates it and
answers every credential failure itself, before DRF is entered, with a bare
``{"message": ...}`` --- that is ``PlatformKeyError``. The one case it does not
reach --- a caller who is authenticated but carries no platform key --- is
answered by the view in that same shape, deliberately, so one declaration covers
both.

The wire carries a second shape that this operation does not publish: anything
DRF raises after that point goes through the project exception handler and comes
back as ``{type, errors[]}``, a method this view does not implement being the
reachable case. That is not declared here on purpose --- attaching a 405 to the
``get`` operation would describe a response ``GET`` cannot produce, since
OpenAPI hangs responses off operations rather than paths.
"""

from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from drf_standardized_errors.openapi import AutoSchema as StandardizedErrorsAutoSchema
from rest_framework import serializers

from platform_api.models import ApiKeyPermission

#: The statuses this operation answers from the authentication middleware, in
#: ``PlatformKeyError`` shape.
_MIDDLEWARE_ANSWERED_STATUSES = frozenset({"401", "403"})


class PlatformKeyAutoSchema(StandardizedErrorsAutoSchema):
    """The project schema class, with the injected error examples narrowed.

    ``drf_standardized_errors`` appends an example of the exception handler's
    ``{type, errors[]}`` body to every 4xx/5xx response, keyed on the status
    code alone and never on the declared serializer
    (``drf_standardized_errors/openapi.py:343-356``). Where this operation
    declares ``PlatformKeyError`` that example contradicts the ``$ref`` beside
    it, and a reader following it writes ``errors[0].code`` and gets a
    ``KeyError`` on the wire. The narrowing is by status rather than blanket so
    that a response later declared with the handler's own shape keeps the
    example that is correct for it.
    """

    def _get_examples(
        self, serializer, direction, media_type, status_code=None, extras=None
    ):
        if direction == "response" and str(status_code) in _MIDDLEWARE_ANSWERED_STATUSES:
            # Skip the standardized-errors override, not the whole chain.
            return super(StandardizedErrorsAutoSchema, self)._get_examples(
                serializer, direction, media_type, status_code, extras
            )
        return super()._get_examples(
            serializer, direction, media_type, status_code, extras
        )


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
    of the per-field structure the organisation-scoped endpoints return. It is
    the shape of this operation's credential failures specifically, not of
    every failure it can return.
    """

    message = serializers.CharField(help_text="Human-readable reason for the refusal.")


WHOAMI_SUMMARY = "Resolve the organisation a platform key belongs to"

WHOAMI_DESCRIPTION = (
    "Takes a platform API key and nothing else: the organisation is read from "
    "the key itself, so this route carries no organisation segment. Call it "
    "once and store `organization_id`; every other endpoint takes it as a path "
    "segment.\n\n"
    "An API deployment key is rejected as unauthenticated — it authenticates "
    "against a different table, on a path that never reaches this endpoint.\n\n"
    "This route serves GET only.\n\n"
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
        summary=WHOAMI_SUMMARY,
        tags=["identity"],
        auth=[{"platformKey": []}],
        responses={
            200: WhoAmIResponse,
            401: OpenApiResponse(
                PlatformKeyError,
                description="No usable platform API key was supplied — absent, "
                "malformed, unknown, or revoked.",
            ),
            # No 403. Every route to one is closed on the published path: the
            # belongs-to-org guard is skipped (the whitelist leaves
            # organization_id None), `ApiKeyPermission.allows` admits GET at
            # every tier, and an unknown tier is barred by the check constraint
            # in migration 0003. The organisation-qualified alias *can* 403, but
            # it is not a published path -- see the identity test that pins the
            # spec to organisation-free paths.
            500: OpenApiResponse(
                description="The request could not be served. The body is not "
                "guaranteed to be JSON.",
            ),
        },
        description=WHOAMI_DESCRIPTION,
    ),
)
