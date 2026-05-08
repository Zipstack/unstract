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


class UsageRecordCreateSerializer(serializers.Serializer):
    """Worker-emitted usage record. Required fields anchor billing-critical attribution."""

    adapter_instance_id = serializers.CharField(required=True, allow_blank=False)
    model_name = serializers.CharField(required=True, allow_blank=False)
    usage_type = serializers.CharField(required=True, allow_blank=False)

    workflow_id = serializers.CharField(required=False, allow_blank=True, default="")
    execution_id = serializers.CharField(required=False, allow_blank=True, default="")
    run_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    llm_usage_reason = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None
    )
    embedding_tokens = serializers.IntegerField(required=False, default=0)
    prompt_tokens = serializers.IntegerField(required=False, default=0)
    completion_tokens = serializers.IntegerField(required=False, default=0)
    total_tokens = serializers.IntegerField(required=False, default=0)
    cost_in_dollars = serializers.FloatField(required=False, default=0.0)
    project_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    prompt_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    execution_time_ms = serializers.IntegerField(
        required=False, allow_null=True, default=None
    )
    status = serializers.CharField(required=False, allow_null=True, default=None)
    error_message = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None
    )
    # Opaque carrier forwarded to post-write hooks; OSS never reads it.
    cloud_extras = serializers.DictField(required=False, allow_null=True, default=None)


class UsageBatchCreateSerializer(serializers.Serializer):
    records = UsageRecordCreateSerializer(many=True, allow_empty=True)
