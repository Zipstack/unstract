"""Search provider contract.

A provider answers one result type. It owns two things the endpoint cannot
know: which rows the caller may open (it must apply the same visibility rule
as that type's own list) and how a row becomes a result. Ranking is shared,
see :mod:`global_search.ranking`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from django.db.models import Model, QuerySet

from global_search.constants import MatchTier
from global_search.ranking import RANK_ANNOTATION, rank_queryset


@dataclass(frozen=True)
class SearchHit:
    id: str
    name: str
    match: MatchTier
    # Required: every route needs at least the id the frontend opens.
    route_params: dict[str, str]
    context: str | None = None


class SearchProvider(ABC):
    """One result type in the search response.

    Subclasses set ``type_key`` (stable contract key), ``label`` (display
    text) and ``order`` (rail position; groups are returned ascending).
    """

    type_key: str
    label: str
    order: int

    @property
    def route_key(self) -> str:
        return f"{self.type_key}.detail"

    @abstractmethod
    def search(self, user: Any, query: str, limit: int) -> list[SearchHit]:
        """Return up to ``limit + 1`` hits, best first.

        The extra row lets the caller derive ``has_more`` without a COUNT.
        Must never return a row ``user`` could not open from the type's list.
        """


class ModelSearchProvider(SearchProvider):
    """Provider backed by one ORM query.

    Subclasses implement :meth:`visible_queryset` with the list view's own
    visibility rule, and :meth:`to_hit` to shape a row.
    """

    # Every field matched as "name"; the first is the displayed name.
    name_fields: tuple[str, ...]
    description_field: str | None = None

    @abstractmethod
    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        """Rows ``user`` can see in this type's list, before search."""

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Hook to add context columns without per-row queries."""
        return queryset

    @abstractmethod
    def context(self, obj: Model) -> str | None:
        """One display-only line, or ``None``."""

    def route_params(self, obj: Model) -> dict[str, str]:
        return {"id": str(obj.pk)}

    def search(self, user: Any, query: str, limit: int) -> list[SearchHit]:
        queryset = rank_queryset(
            self.visible_queryset(user),
            query,
            name_fields=self.name_fields,
            description_field=self.description_field,
        )
        return [self.to_hit(obj) for obj in self.annotate(queryset)[: limit + 1]]

    def to_hit(self, obj: Model) -> SearchHit:
        return SearchHit(
            id=str(obj.pk),
            name=getattr(obj, self.name_fields[0]),
            match=MatchTier(getattr(obj, RANK_ANNOTATION)),
            context=self.context(obj),
            route_params=self.route_params(obj),
        )
