"""List filter parameters and ``aggregate/`` response shapes shared by the
deployment and pipeline lists.
"""

import uuid

from django.http import QueryDict
from rest_framework import serializers

from workflow_manager.workflow_v2.list_aggregates import ListFilters, RowStatus

# Detail and write routes keep their own lookups, so the filters skip them.
LIST_FILTER_ACTIONS = ("list", "aggregate")


class ListFilterSerializer(serializers.Serializer):
    """Optional list filters. Combined, a row must match every one given."""

    status = serializers.ChoiceField(
        choices=[status.value for status in RowStatus],
        required=False,
        help_text="Return only rows in this status, which comes from the latest "
        "finished run; `inactive` wins over it.",
    )
    owner = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Return only rows this user owns or co-owns (user id).",
    )
    last_run_after = serializers.DateTimeField(
        required=False,
        help_text="Return only rows whose last run is at or after this time.",
    )
    last_run_before = serializers.DateTimeField(
        required=False,
        help_text="Return only rows whose last run is at or before this time.",
    )
    failing = serializers.BooleanField(
        required=False,
        help_text="When true, return only active rows whose last five finished "
        "runs all ended in error.",
    )

    def validate_status(self, value: str) -> RowStatus:
        return RowStatus(value)


def list_filters_from(params: QueryDict) -> ListFilters:
    """The list filters in ``params``; blank values are ignored, bad ones are a 400."""
    serializer = ListFilterSerializer(data={k: v for k, v in params.items() if v})
    serializer.is_valid(raise_exception=True)
    return ListFilters(**serializer.validated_data)


def workflow_filter_from(params: QueryDict) -> str | None:
    """The ``workflow`` param, ``None`` when blank; not a UUID is a 400."""
    workflow: str | None = params.get("workflow")
    if not workflow:
        return None
    try:
        uuid.UUID(workflow)
    except ValueError:
        # Django raises on evaluation, past the handler that returns the 400.
        raise serializers.ValidationError({"workflow": "Must be a valid UUID."}) from None
    return workflow


class StatusCountsSerializer(serializers.Serializer):
    """Rows per status. They always sum to `total`."""

    success = serializers.IntegerField()
    partial_success = serializers.IntegerField(
        help_text="The latest finished run completed with some files failed."
    )
    error = serializers.IntegerField()
    never_run = serializers.IntegerField()
    inactive = serializers.IntegerField()


class FailingRowSerializer(serializers.Serializer):
    """An active row whose last five finished runs all ended in error."""

    id = serializers.UUIDField(source="row.pk")
    owner_email = serializers.CharField(
        source="row.owner_email",
        allow_null=True,
        help_text="The earliest owner, or null when no owner is a person.",
    )
    failures_in_a_row = serializers.IntegerField()
    failing_since = serializers.DateTimeField()
    last_failure = serializers.DateTimeField()
    last_success = serializers.DateTimeField(allow_null=True)


class ListAggregateSerializer(serializers.Serializer):
    """Counts over every row the list would return for the same filters."""

    total = serializers.IntegerField(help_text="Equals the list's `count`.")
    by_status = StatusCountsSerializer()
    failing_count = serializers.IntegerField()
