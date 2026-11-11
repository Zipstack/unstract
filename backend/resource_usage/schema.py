"""drf-spectacular annotations for the usage endpoints and list parameters.
With README.md, these are the published contract.
"""

from collections.abc import Callable
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from drf_standardized_errors.openapi_serializers import ErrorResponse404Serializer

from resource_usage.constants import ListParam, ProfileKind
from resource_usage.serializers import AdapterUsageSerializer, ConnectorUsageSerializer

USAGE_LIST_PARAMETERS = [
    OpenApiParameter(
        ListParam.WITH_USAGE,
        OpenApiTypes.STR,
        description="`true` (any case) ends each row with `used_in_count` (and, "
        "on connectors, `used_as`), and adds `unused_count` to a paged response. "
        "Any other value is ignored.",
    ),
    OpenApiParameter(
        ListParam.UNUSED,
        OpenApiTypes.STR,
        description="`true` (any case) lists only profiles nothing uses, and "
        "adds the same keys as `with_usage=true`. Any other value is ignored.",
    ),
]


def usage_schema(kind: ProfileKind) -> Callable[[Any], Any]:
    """``extend_schema`` for ``GET <profile>/{id}/usage/``."""
    serializer = (
        ConnectorUsageSerializer
        if kind == ProfileKind.CONNECTOR
        else AdapterUsageSerializer
    )
    return extend_schema(
        operation_id=f"{kind}_usage",
        tags=["resource-usage"],
        responses={
            200: OpenApiResponse(serializer, description="What uses the profile."),
            404: OpenApiResponse(
                ErrorResponse404Serializer,
                description=f"No such {kind} visible to the caller.",
            ),
        },
        description=f"What references the {kind}. See resource_usage/README.md.",
    )
