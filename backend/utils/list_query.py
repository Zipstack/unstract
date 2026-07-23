"""Shared list-query helpers for resource list endpoints.

Provides owner-inclusive ``?search`` and per-column sorting (name / owner /
created) with a ``pk__in`` re-wrap so managers ending in Postgres ``DISTINCT
ON`` can still be ordered by an arbitrary column.
"""

from typing import Any

from django.db.models import Model, Q, QuerySet
from rest_framework.request import Request

# ``name`` maps to the resource-specific name field each caller passes;
# owner/created are shared across every list endpoint.
OWNER_SORT_FIELD = "created_by__email"
CREATED_SORT_FIELD = "created_at"


def apply_search_and_sort(
    queryset: QuerySet[Any],
    *,
    model: type[Model],
    name_field: str,
    request: Request,
    select_related: tuple[str, ...] = (),
    prefetch_related: tuple[str, ...] = (),
    default_sort_by: str = "name",
) -> QuerySet[Any]:
    """Apply owner-inclusive ``?search`` and ``?sort_by``/``?order`` to a list
    queryset.

    ``sort_by`` is ``name`` | ``owner`` | ``created`` (default ``name``);
    ``order`` is ``asc`` | ``desc`` (default ``asc``). The queryset is re-wrapped
    via ``pk__in`` to drop any ``DISTINCT ON`` (so ordering by a non-distinct
    column is legal) and a ``pk`` tiebreaker is appended for stable pagination.
    ``select_related`` / ``prefetch_related`` are re-attached to the re-wrapped
    queryset to keep the list free of N+1 owner/co-owner lookups.

    Args:
        queryset: The already org-scoped, ``for_user``-filtered list queryset.
        model: The concrete resource model, used to re-wrap via ``pk__in``.
        name_field: The resource's name column (e.g. ``adapter_name``).
        request: DRF request carrying ``search`` / ``sort_by`` / ``order``.
        select_related: FK joins to re-attach after the re-wrap.
        prefetch_related: Reverse/M2M prefetches to re-attach after the re-wrap.
        default_sort_by: Sort key used when ``?sort_by`` is absent.

    Returns:
        An ordered queryset ready for pagination.
    """
    params = request.query_params

    search = params.get("search")
    if search:
        queryset = queryset.filter(
            Q(**{f"{name_field}__icontains": search})
            | Q(**{f"{OWNER_SORT_FIELD}__icontains": search})
        )

    sort_field = {
        "name": name_field,
        "owner": OWNER_SORT_FIELD,
        "created": CREATED_SORT_FIELD,
    }.get(params.get("sort_by") or default_sort_by, name_field)
    order_prefix = "-" if (params.get("order") or "asc").lower() == "desc" else ""

    # Ordering the source by ``pk`` keeps the DISTINCT ON (always the pk) valid
    # while stripping the model's default ordering, so the outer query is free
    # to sort by any column.
    rewrapped = model.objects.filter(pk__in=queryset.order_by("pk").values("pk"))
    if select_related:
        rewrapped = rewrapped.select_related(*select_related)
    if prefetch_related:
        rewrapped = rewrapped.prefetch_related(*prefetch_related)
    return rewrapped.order_by(f"{order_prefix}{sort_field}", "pk")
