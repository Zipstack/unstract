from typing import Any

from django.db.models import QuerySet
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.pagination import OptionalPagination

from connection_check.constants import ListParam
from connection_check.filters import failing


class FailingCountPagination(OptionalPagination):
    """``OptionalPagination`` that adds ``failing_count`` to the paged envelope.

    Counted across all pages over the view's ``get_status_base_queryset()``:
    every list filter except ``failing`` and ``last_test_status``, so the
    count stays put while those change. A bare-array response is unchanged.
    """

    view: Any = None

    def paginate_queryset(
        self, queryset: QuerySet, request: Request, view: APIView | None = None
    ) -> Any:
        self.view = view
        return super().paginate_queryset(queryset, request, view=view)

    def get_paginated_response(self, data: Any) -> Response:
        response: Response = super().get_paginated_response(data)
        base = self.view.filter_queryset(self.view.get_status_base_queryset())
        response.data[ListParam.FAILING_COUNT] = failing(base).count()
        return response

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        paged: dict[str, Any] = super().get_paginated_response_schema(schema)
        paged["properties"][ListParam.FAILING_COUNT] = {
            "type": "integer",
            "description": "Failing profiles across all pages, ignoring the "
            "failing and last_test_status filters.",
            "example": 2,
        }
        return paged
