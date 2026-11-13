"""The adapter and connector list pagination, with ``unused_count`` in its
published envelope schema.
"""

from typing import Any

from connection_check.pagination import FailingCountPagination

from resource_usage.constants import ListParam


class UsageCountPagination(FailingCountPagination):
    """``FailingCountPagination`` whose schema also declares ``unused_count``.

    ``ProfileUsageMixin.list`` adds the key, and only when usage is requested,
    so the schema lists it as optional. Responses are unchanged.
    """

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        paged = super().get_paginated_response_schema(schema)
        paged["properties"][ListParam.UNUSED_COUNT] = {
            "type": "integer",
            "description": "Only with with_usage=true or unused=true: profiles "
            "nothing uses, across all pages, ignoring the unused, failing and "
            "last_test_status filters.",
            "example": 3,
        }
        return paged
