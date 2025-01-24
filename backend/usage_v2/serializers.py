from rest_framework import serializers
from tags.serializers import TagParamsSerializer

from .models import Usage


class GetUsageSerializer(serializers.Serializer):
    run_id = serializers.CharField(required=True)


class UsageMetricsSerializer(TagParamsSerializer):
    execution_id = serializers.CharField(required=False)
    file_execution_id = serializers.CharField(required=False)


class UsageSerializer(serializers.ModelSerializer):
    workflow_execution_id = serializers.UUIDField(read_only=True)
    tag = serializers.CharField(read_only=True)
    executed_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Usage
        fields = "__all__"
