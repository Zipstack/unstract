from typing import Any

from django.db.models import QuerySet
from django.http import QueryDict

from connection_check.constants import NEVER_TESTED, ConnectionStatus, ListParam

_STATUS_LOOKUPS: dict[str, dict[str, Any]] = {
    ConnectionStatus.CONNECTED: {"test_result__status": ConnectionStatus.CONNECTED},
    ConnectionStatus.FAILED: {"test_result__status": ConnectionStatus.FAILED},
    NEVER_TESTED: {"test_result__isnull": True},
}


def failing(queryset: QuerySet) -> QuerySet:
    """Profiles whose latest test failed."""
    return queryset.filter(**_STATUS_LOOKUPS[ConnectionStatus.FAILED])


def filter_by_test_status(queryset: QuerySet, params: QueryDict) -> QuerySet:
    """Apply the optional ``failing`` and ``last_test_status`` list filters.

    Unknown values are ignored.
    """
    if params.get(ListParam.FAILING, "").lower() == "true":
        queryset = failing(queryset)
    lookup = _STATUS_LOOKUPS.get(params.get(ListParam.LAST_TEST_STATUS, ""))
    return queryset.filter(**lookup) if lookup else queryset
