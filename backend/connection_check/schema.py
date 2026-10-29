"""drf-spectacular annotations for the test-and-record endpoints and list
filters. With README.md, these are the published contract.
"""

from collections.abc import Callable
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from drf_standardized_errors.openapi_serializers import (
    ErrorResponse403Serializer,
    ErrorResponse404Serializer,
)

from connection_check.constants import NEVER_TESTED, ConnectionStatus, ListParam
from connection_check.serializers import ConnectionCheckResultSerializer

LIST_FILTER_PARAMETERS = [
    OpenApiParameter(
        ListParam.FAILING,
        OpenApiTypes.STR,
        description="`true` (any case) lists only profiles whose latest test "
        "failed. Any other value is ignored.",
    ),
    OpenApiParameter(
        ListParam.LAST_TEST_STATUS,
        OpenApiTypes.STR,
        enum=[ConnectionStatus.CONNECTED, ConnectionStatus.FAILED, NEVER_TESTED],
        description="Lists only profiles with this status. Any other value is "
        "ignored.",
    ),
]


def connection_test_schema(profile: str) -> Callable[[Any], Any]:
    """``extend_schema`` for ``POST <profile>/{id}/test/``."""
    return extend_schema(
        operation_id=f"{profile}_test_and_record",
        tags=["connection-check"],
        request=None,
        responses={
            200: OpenApiResponse(
                ConnectionCheckResultSerializer,
                description="Tested and stored; a failed test is also a 200.",
            ),
            403: OpenApiResponse(
                ErrorResponse403Serializer,
                description=f"The caller may not edit this {profile}.",
            ),
            404: OpenApiResponse(
                ErrorResponse404Serializer,
                description=f"No such {profile} visible to the caller.",
            ),
        },
        description=f"Test the saved {profile} and store the result. "
        "See connection_check/README.md.",
    )
