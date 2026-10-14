import logging
from contextlib import nullcontext
from typing import Any

from django.db import (
    Error,
    InterfaceError,
    OperationalError,
    connection,
    transaction,
)
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from global_search.constants import SearchParams
from global_search.exceptions import SearchFailed, SearchUnavailable
from global_search.providers import SearchProvider
from global_search.registry import get_providers
from global_search.serializers import SearchQuerySerializer, SearchResponseSerializer

logger = logging.getLogger(__name__)

# Database errors a retry may clear (unreachable, timed out, locked,
# deadlocked), as opposed to a bug.
_RETRYABLE = (InterfaceError, OperationalError)


def _connection_unusable(error: Exception) -> bool:
    """Whether later types would fail too: a savepoint that could not be
    rolled back (ATOMIC_REQUESTS), or a database error after which the
    connection no longer answers. A statement timeout, lock timeout or
    deadlock is an OperationalError on a healthy connection, so the class
    alone does not decide; ``is_usable()`` runs only on this error path.
    """
    if connection.needs_rollback:
        return True
    # django.db.Error, not DatabaseError: InterfaceError ("connection
    # already closed") derives from Error only.
    if not isinstance(error, Error):
        return False
    if connection.connection is None:
        # No open connection after a connection-class error: connecting
        # failed, so every later type would dial a dead database too.
        return isinstance(error, _RETRYABLE)
    return not connection.is_usable()


def _group(provider: SearchProvider, user: Any, query: str, limit: int) -> dict | None:
    hits = provider.search(user, query, limit)
    if not hits:
        return None
    return {
        "type": provider.type_key,
        "label": provider.label,
        "has_more": len(hits) > limit,
        "results": [
            {
                "type": provider.type_key,
                "id": hit.id,
                "name": hit.name,
                "context": hit.context,
                "match": hit.match.label,
                "route": {"key": provider.route_key, "params": hit.route_params},
            }
            for hit in hits[:limit]
        ],
    }


class GlobalSearchView(APIView):
    """Search every resource type the caller can open, grouped by type."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[SearchQuerySerializer],
        responses={
            200: SearchResponseSerializer,
            400: OpenApiResponse(description="Invalid parameters (validation_error)."),
            500: OpenApiResponse(
                description=(
                    "search_failed: every searched type failed, not all with "
                    "retryable database errors (a bug). Retrying will not help."
                )
            ),
            503: OpenApiResponse(
                description=(
                    "search_unavailable: every searched type failed with a "
                    "database error a retry may clear (unreachable, timed out, "
                    "locked), or a failure left the connection unusable. "
                    "Retry; never show as 'no results'."
                )
            ),
        },
        description=(
            "Groups come back in rail order with empty groups omitted. Each "
            "type applies its own list's visibility rule. See "
            "backend/global_search/README.md for the type vocabulary and the "
            "response-time budget."
        ),
    )
    def get(self, request: Request) -> Response:
        params = SearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query: str = params.validated_data["q"]
        wanted: list[str] = params.validated_data["types"]
        limit: int = params.validated_data["limit"]

        groups = []
        failed_types: list[str] = []
        attempted = 0
        errors: list[Exception] = []
        if len(query) >= SearchParams.MIN_QUERY_LENGTH:
            for provider in get_providers():
                if wanted and provider.type_key not in wanted:
                    continue
                attempted += 1
                # Under ATOMIC_REQUESTS a failed query aborts the request's
                # transaction; a savepoint keeps it from poisoning the next type.
                guard = (
                    transaction.atomic() if connection.in_atomic_block else nullcontext()
                )
                try:
                    with guard:
                        group = _group(provider, request.user, query, limit)
                except Exception as error:
                    logger.exception(
                        "Global search provider '%s' failed", provider.type_key
                    )
                    # Every later type would fail too: fail the request
                    # instead of blaming healthy types. The cause is logged
                    # above, so it is not chained into the handler's log.
                    if _connection_unusable(error):
                        raise SearchUnavailable() from None
                    # Providers can come from other apps (cloud); one failing
                    # type drops its own group and is named in failed_types.
                    failed_types.append(provider.type_key)
                    errors.append(error)
                    continue
                if group:
                    groups.append(group)

        # Every type failing is never "no matches". Each cause is logged
        # above; only database errors a retry may clear are worth retrying.
        if errors and len(errors) == attempted:
            if all(isinstance(e, _RETRYABLE) for e in errors):
                raise SearchUnavailable() from None
            raise SearchFailed() from None

        return Response({"query": query, "groups": groups, "failed_types": failed_types})
