from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from workflow_manager.execution.abort import MAX_ABORT_IDS
from workflow_manager.execution.enum import AbortOutcome
from workflow_manager.execution.serializer.execution import ExecutionSerializer


@extend_schema_serializer(component_name="ExecutionListRow")
class StuckExecutionSerializer(ExecutionSerializer):
    """An execution row plus ``stuck_since``, served for ``?stuck=true``.

    Also the list's documented row, where ``stuck_since`` is optional.
    """

    # Not read-only, so the schema can mark it optional.
    stuck_since = serializers.DateTimeField(
        required=False,
        help_text="Time of last activity on the run or its files; only with stuck=true.",
    )


class StuckExecutionCountsSerializer(serializers.Serializer):
    API = serializers.IntegerField()
    ETL = serializers.IntegerField()
    TASK = serializers.IntegerField()
    WF = serializers.IntegerField()


class StuckExecutionCountSerializer(serializers.Serializer):
    threshold_seconds = serializers.IntegerField()
    total = serializers.IntegerField()
    counts = StuckExecutionCountsSerializer()


class ExecutionAbortRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=MAX_ABORT_IDS,
        help_text=f"1 to {MAX_ABORT_IDS} execution ids; duplicates are removed.",
    )


class ExecutionAbortResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=[o.value for o in AbortOutcome])
    status = serializers.CharField(
        allow_null=True, help_text="The run's status; null when not_permitted or failed."
    )


class ExecutionAbortResponseSerializer(serializers.Serializer):
    results = ExecutionAbortResultSerializer(many=True)
    aborted = serializers.IntegerField()
    already_finished = serializers.IntegerField()
    not_permitted = serializers.IntegerField()
    failed = serializers.IntegerField()
