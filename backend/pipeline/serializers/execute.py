import logging

from pipeline.models import Pipeline
from rest_framework import serializers

logger = logging.getLogger(__name__)


class PipelineExecuteSerializer(serializers.Serializer):
    # TODO: Add pipeline as a read_only related field
    pipeline_id = serializers.UUIDField()
    execution_id = serializers.UUIDField(required=False)

    def validate_pipeline_id(self, value: str) -> str:
        try:
            Pipeline.objects.get(pk=value)
        except Pipeline.DoesNotExist:
            raise serializers.ValidationError("Invalid pipeline ID")
        return value


class DateRangeSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
