from pipeline_v2.models import Pipeline
from rest_framework import serializers


class PipelineUpdateSerializer(serializers.Serializer):
    pipeline_id = serializers.UUIDField(required=True)
    active = serializers.BooleanField(required=True)

    def validate_pipeline_id(self, value: str) -> str:
        try:
            Pipeline.objects.get(pk=value)
        except Pipeline.DoesNotExist:
            raise serializers.ValidationError("Invalid pipeline ID")
        return value
