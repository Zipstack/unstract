from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from global_search.constants import SearchParams
from global_search.providers import SearchProvider
from global_search.registry import get_providers
from global_search.serializers import SearchQuerySerializer, SearchResponseSerializer


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
        responses=SearchResponseSerializer,
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
        if len(query) >= SearchParams.MIN_QUERY_LENGTH:
            for provider in get_providers():
                if wanted and provider.type_key not in wanted:
                    continue
                group = _group(provider, request.user, query, limit)
                if group:
                    groups.append(group)

        return Response({"query": query, "groups": groups})
