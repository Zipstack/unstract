from collections import OrderedDict
from typing import Any, Union
import uuid

from api_v2.constants import ApiExecution
from api_v2.models import APIDeployment, APIKey
from django.core.validators import RegexValidator
from pipeline_v2.models import Pipeline
from rest_framework.serializers import (
    BooleanField,
    CharField,
    IntegerField,
    JSONField,
    ModelSerializer,
    Serializer,
    ValidationError,
)
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin

from backend.serializers import AuditSerializer


class APIDeploymentSerializer(IntegrityErrorMixin, AuditSerializer):
    class Meta:
        model = APIDeployment
        fields = "__all__"

    unique_error_message_map: dict[str, dict[str, str]] = {
        "unique_api_name": {
            "field": "api_name",
            "message": (
                "This API name is already in use. Please select a different name."
            ),
        },
        "api_deployment_api_endpoint_key": {
            "field": "api_name",
            "message": (
                "This API name is already in use. Please select a different name."
            ),
        },
    }

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

    def validate(self, data):
        api = data.get("api")
        pipeline = data.get("pipeline")

        if api and pipeline:
            raise ValidationError(
                "Only one of `api` or `pipeline` should be set, not both."
            )
        elif not api and not pipeline:
            raise ValidationError("At least one of `api` or `pipeline` must be set.")

        return data

    def to_representation(self, instance: APIKey) -> OrderedDict[str, Any]:
        """Override the to_representation method to include additional
        context."""
        deployment: Union[APIDeployment, Pipeline] = self.context.get("deployment")
        representation: OrderedDict[str, Any] = super().to_representation(instance)

        if deployment:
            # Handle APIDeployment and Pipeline separately
            if isinstance(deployment, APIDeployment):
                representation["api"] = deployment.id
                representation["pipeline"] = None
                representation["description"] = f"API Key for {deployment.api_name}"
            elif isinstance(deployment, Pipeline):
                representation["api"] = None
                representation["pipeline"] = deployment.id
                representation["description"] = (
                    f"API Key for {deployment.pipeline_name}"
                )
            else:
                raise ValueError(
                    "Context must be an instance of APIDeployment or Pipeline"
                )

            representation["is_active"] = True

        return representation


class ExecutionRequestSerializer(Serializer):
    """Execution request serializer.

    Attributes:
        timeout (int): Timeout for the API deployment, maximum value can be 300s.
            If -1 it corresponds to async execution. Defaults to -1
        include_metadata (bool): Flag to include metadata in API response
        use_file_history (bool): Flag to use FileHistory to save and retrieve
            responses quickly. This is undocumented to the user and can be
            helpful for demos.
    """

    timeout = IntegerField(
        min_value=-1, max_value=ApiExecution.MAXIMUM_TIMEOUT_IN_SEC, default=-1
    )
    include_metadata = BooleanField(default=False)
    use_file_history = BooleanField(default=False)

class ExecutionQuerySerializer(Serializer):
    execution_id = CharField(required=True)
    include_metadata = BooleanField(default=False)

    def validate_execution_id(self, value):
        """Trim spaces and validate execution_id as UUID."""
        value = value.strip()
        try:
            uuid.UUID(value)
        except ValueError:
            raise ValidationError("Invalid execution_id. Must be a valid UUID.")
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
            "pipeline",
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
