from collections import OrderedDict
from typing import Any, Union

from api.constants import ApiExecution
from api.models import APIDeployment, APIKey
from backend.serializers import AuditSerializer
from django.core.validators import RegexValidator
from rest_framework.serializers import (
    CharField,
    IntegerField,
    JSONField,
    ModelSerializer,
    Serializer,
    ValidationError,
)


class APIDeploymentSerializer(AuditSerializer):
    class Meta:
        model = APIDeployment
        fields = "__all__"

    def validate_api_name(self, value: str) -> str:
        api_name_validator = RegexValidator(
            regex=r"^[a-zA-Z0-9_-]+$",
            message="Only letters, numbers, hyphen and \
                underscores are allowed.",
            code="invalid_api_name",
        )
        api_name_validator(value)
        return value


class APIKeySerializer(AuditSerializer):
    class Meta:
        model = APIKey
        fields = "__all__"

    def to_representation(self, instance: APIKey) -> OrderedDict[str, Any]:
        """Override the to_representation method to include additional
        context."""
        context = self.context.get("context", {})
        deployment: APIDeployment = context.get("deployment")
        representation: OrderedDict[str, Any] = super().to_representation(
            instance
        )
        if deployment:
            representation["api"] = deployment.id
            representation["description"] = f"API Key for {deployment.name}"
            representation["is_active"] = True

        return representation


class ExecutionRequestSerializer(Serializer):
    """Execution request serializer
    timeout: 0: maximum value of timeout, -1: async execution
    """

    timeout = IntegerField(
        min_value=-1, max_value=ApiExecution.MAXIMUM_TIMEOUT_IN_SEC, default=-1
    )

    def validate_timeout(self, value: Any) -> int:
        if not isinstance(value, int):
            raise ValidationError("timeout must be a integer.")
        if value == 0:
            value = ApiExecution.MAXIMUM_TIMEOUT_IN_SEC
        return value

    def get_timeout(self, validated_data: dict[str, Union[int, None]]) -> int:
        value = validated_data.get("timeout", -1)
        if not isinstance(value, int):
            raise ValidationError("timeout must be a integer.")
        return value


class APIDeploymentListSerializer(ModelSerializer):
    workflow_name = CharField(source="workflow.workflow_name", read_only=True)

    class Meta:
        model = APIDeployment
        fields = [
            "id",
            "workflow",
            "workflow_name",
            "display_name",
            "description",
            "is_active",
            "api_endpoint",
            "api_name",
            "created_by",
        ]


class APIKeyListSerializer(ModelSerializer):
    class Meta:
        model = APIKey
        fields = [
            "id",
            "created_at",
            "modified_at",
            "api_key",
            "is_active",
            "description",
            "api",
        ]


class DeploymentResponseSerializer(Serializer):
    is_active = CharField()
    id = CharField()
    api_key = CharField()
    api_endpoint = CharField()
    display_name = CharField()
    description = CharField()
    api_name = CharField()


class APIExecutionResponseSerializer(Serializer):
    execution_status = CharField()
    status_api = CharField()
    error = CharField()
    result = JSONField()
