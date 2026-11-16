from rest_framework import serializers
from workflow_manager.workflow_v2.list_aggregate_serializers import (
    FailingRowSerializer,
    ListAggregateSerializer,
)


class FailingPipelineSerializer(FailingRowSerializer):
    """An active pipeline whose last five finished runs all ended in error."""

    name = serializers.CharField(source="row.pipeline_name")
    pipeline_type = serializers.CharField(source="row.pipeline_type")
    next_run_time = serializers.DateTimeField(source="row.next_run_time", allow_null=True)


class PipelineAggregateSerializer(ListAggregateSerializer):
    """Pipelines per status, and the ones failing."""

    not_scheduled = serializers.IntegerField(
        help_text="Active pipelines with no schedule. Overlaps `by_status`."
    )
    failing = FailingPipelineSerializer(many=True)
