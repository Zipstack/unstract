"""Shared ranking: prefix before substring, name before description.

Both an ORM form (one SQL query per type) and an in-memory form (for
providers whose source is not a single queryset) so every type ranks alike.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from global_search.constants import MatchTier

RANK_ANNOTATION = "_search_rank"

T = TypeVar("T")


def _any(fields: Iterable[str], lookup: str, query: str) -> Q:
    condition = Q()
    for field_name in fields:
        condition |= Q(**{f"{field_name}__{lookup}": query})
    return condition


def rank_queryset(
    queryset: QuerySet[Any],
    query: str,
    *,
    name_fields: tuple[str, ...],
    description_field: str | None = None,
) -> QuerySet[Any]:
    """Filter ``queryset`` to rows matching ``query`` and order them by tier,
    then most recently modified, then pk so equal tiers page deterministically.

    ``icontains``/``istartswith`` escape ``%`` and ``_``, so user input is
    always matched literally.
    """
    tiers = [
        When(_any(name_fields, "istartswith", query), then=Value(MatchTier.NAME_PREFIX)),
        When(_any(name_fields, "icontains", query), then=Value(MatchTier.NAME)),
    ]
    matches = _any(name_fields, "icontains", query)
    if description_field:
        tiers += [
            When(
                Q(**{f"{description_field}__istartswith": query}),
                then=Value(MatchTier.DESCRIPTION_PREFIX),
            ),
            When(
                Q(**{f"{description_field}__icontains": query}),
                then=Value(MatchTier.DESCRIPTION),
            ),
        ]
        matches |= Q(**{f"{description_field}__icontains": query})

    return (
        queryset.filter(matches)
        .annotate(**{RANK_ANNOTATION: Case(*tiers, output_field=IntegerField())})
        .order_by(RANK_ANNOTATION, "-modified_at", "pk")
    )


def match_tier(
    query: str, names: Iterable[str | None], description: str | None = None
) -> MatchTier | None:
    """In-memory equivalent of the ``rank_queryset`` tiers; ``None`` means no
    match. Comparison is case-insensitive via ``casefold``.
    """
    needle = query.casefold()
    names = [n.casefold() for n in names if n]
    if any(n.startswith(needle) for n in names):
        return MatchTier.NAME_PREFIX
    if any(needle in n for n in names):
        return MatchTier.NAME
    if description:
        desc = description.casefold()
        if desc.startswith(needle):
            return MatchTier.DESCRIPTION_PREFIX
        if needle in desc:
            return MatchTier.DESCRIPTION
    return None


def rank_items(
    items: Iterable[T],
    query: str,
    *,
    names: Callable[[T], Iterable[str | None]],
    description: Callable[[T], str | None] = lambda _: None,
    sort_key: Callable[[T], Any],
) -> list[tuple[T, MatchTier]]:
    """Filter and order ``items`` like :func:`rank_queryset`. ``sort_key``
    breaks ties within a tier and must be total, for deterministic order.
    """
    ranked = []
    for item in items:
        tier = match_tier(query, names(item), description(item))
        if tier is not None:
            ranked.append((item, tier))
    ranked.sort(key=lambda pair: (pair[1], sort_key(pair[0])))
    return ranked
