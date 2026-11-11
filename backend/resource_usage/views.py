"""The usage action and the opt-in list fields, shared by the adapter and
connector viewsets.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from resource_usage.constants import ListParam, ProfileKind
from resource_usage.references import ProfileUsage, collect
from resource_usage.serializers import usage_payload


def _is_true(value: str | None) -> bool:
    return (value or "").lower() == "true"


class ProfileUsageMixin:
    """Adds ``GET <profile>/{id}/usage/`` and, on request, usage on the list.

    The list is unchanged unless the caller passes ``with_usage=true`` or
    ``unused=true``. Then each row ends with ``used_in_count`` (and, for
    connectors, ``used_as``) and a paged response with ``unused_count``.
    ``unused=true`` also lists only profiles nothing uses.

    The viewset sets ``usage_kind``, lists in ``usage_fields`` every profile
    column a usage provider reads, and defines ``get_status_base_queryset``,
    which the list queryset must only narrow.
    """

    usage_kind: ProfileKind
    # Profile columns the usage providers read.
    usage_fields: tuple[str, ...] = ("id", "organization")
    request: Request
    action: str | None

    def usage_requested(self) -> bool:
        params = self.request.query_params
        return _is_true(params.get(ListParam.WITH_USAGE)) or _is_true(
            params.get(ListParam.UNUSED)
        )

    def _list_usage(self) -> dict[Any, ProfileUsage]:
        """Usage of every profile the list could show, worked out once per
        request: the rows, the ``unused`` filter and ``unused_count`` share it.
        """
        cached: dict[Any, ProfileUsage] | None = getattr(self, "_usage_index", None)
        if cached is None:
            base = self.filter_queryset(self.get_status_base_queryset())  # type: ignore[attr-defined]
            # Plain rows: the providers read only these columns, and skipping
            # the rest avoids decrypting every profile's stored settings.
            # The index needs no ordering.
            profiles = list(
                base.order_by()
                .select_related(None)
                .prefetch_related(None)
                .only(*self.usage_fields)
            )
            cached = collect(self.usage_kind, profiles)
            self._usage_index = cached
        return cached

    def filter_by_usage(self, queryset: QuerySet) -> QuerySet:
        """Apply ``unused=true`` to the list queryset."""
        if not _is_true(self.request.query_params.get(ListParam.UNUSED)):
            return queryset
        unused = [
            pk for pk, usage in self._list_usage().items() if not usage.used_in_count
        ]
        return queryset.filter(pk__in=unused)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not self.usage_requested():
            return super().list(request, *args, **kwargs)  # type: ignore[misc]
        # Work out usage before reading the rows, so a profile deleted or
        # unshared in between is missing from the rows, not from the index.
        index = self._list_usage()
        response: Response = super().list(request, *args, **kwargs)  # type: ignore[misc]
        paged = isinstance(response.data, dict)
        rows = response.data["results"] if paged else response.data
        # Rows carry the pk as a string; the index keys are UUIDs.
        by_pk = {str(pk): usage for pk, usage in index.items()}
        for row in rows:
            # Every row is in the index: the list only narrows its base, and
            # the index was read first.
            usage = by_pk[str(row["id"])]
            row[ListParam.USED_IN_COUNT] = usage.used_in_count
            if self.usage_kind == ProfileKind.CONNECTOR:
                row[ListParam.USED_AS] = usage.used_as
        if paged:
            response.data[ListParam.UNUSED_COUNT] = sum(
                1 for usage in index.values() if not usage.used_in_count
            )
        return response

    @action(detail=True, methods=["get"], url_path="usage")
    def usage(self, request: Request, pk: str | None = None) -> Response:
        profile = self.get_object()  # type: ignore[attr-defined]
        usage = collect(self.usage_kind, [profile], with_derived=True)[profile.pk]
        return Response(usage_payload(self.usage_kind, profile, usage, request.user))


__all__ = ["ProfileUsageMixin"]
