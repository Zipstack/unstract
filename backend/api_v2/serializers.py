import re
import uuid
from collections import OrderedDict
from typing import Any

from django.core.validators import RegexValidator
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from rest_framework.serializers import (
    BooleanField,
    CharField,
    FileField,
    IntegerField,
    JSONField,
    ListField,
    ModelSerializer,
    Serializer,
    ValidationError,
)
from tags.serializers import TagParamsSerializer
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin
from workflow_manager.workflow_v2.exceptions import ExecutionDoesNotExistError
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from api_v2.constants import ApiExecution
from api_v2.models import APIDeployment, APIKey
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

    def validate(self, data):
        """Validate that only one API deployment per workflow is allowed for new deployments."""
        workflow = data.get("workflow")

        # Only apply this validation for new deployments (not updates)
        if workflow and not self.instance:
            # Check if this workflow already has an active API deployment
            existing_active_count = APIDeployment.objects.filter(
                workflow=workflow, is_active=True
            ).count()

            # If there's already an active API deployment, prevent creating a new one
            if existing_active_count > 0:
                raise ValidationError(
                    {
                        "workflow": "This workflow already has an active API deployment. Only one API deployment per workflow is allowed."
                    }
                )

        return data


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
        context.
        """
        deployment: APIDeployment | Pipeline = self.context.get("deployment")
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
                representation["description"] = f"API Key for {deployment.pipeline_name}"
            else:
                raise ValueError(
                    "Context must be an instance of APIDeployment or Pipeline"
                )

            representation["is_active"] = True

        return representation


class ExecutionRequestSerializer(TagParamsSerializer):
    """Execution request serializer.

    Attributes:
        timeout (int): Timeout for the API deployment, maximum value can be 300s.
            If -1 it corresponds to async execution. Defaults to -1
        include_metadata (bool): Flag to include metadata in API response
        include_metrics (bool): Flag to include metrics in API response
        use_file_history (bool): Flag to use FileHistory to save and retrieve
            responses quickly. This is undocumented to the user and can be
            helpful for demos.
        tags (str): Comma-separated List of tags to associate with the execution.
            e.g:'tag1,tag2-name,tag3_name'
        llm_profile_id (str): UUID of the LLM profile to override the default profile.
            If not provided, the default profile will be used.
        hitl_queue_name (str, optional): Document class name for manual review queue.
            If not provided, uses API name as document class.
    """

    MAX_FILES_ALLOWED = 32

    timeout = IntegerField(
        min_value=-1, max_value=ApiExecution.MAXIMUM_TIMEOUT_IN_SEC, default=-1
    )
    include_metadata = BooleanField(default=False)
    include_metrics = BooleanField(default=False)
    use_file_history = BooleanField(default=False)
    llm_profile_id = CharField(required=False, allow_null=True, allow_blank=True)
    hitl_queue_name = CharField(required=False, allow_null=True, allow_blank=True)

    def validate_hitl_queue_name(self, value: str | None) -> str | None:
        """Validate queue name format: a-z0-9-_ with length and pattern restrictions."""
        if not value:
            return value

        # Length validation
        if len(value) < 3:
            raise ValidationError("Queue name must be at least 3 characters long.")
        if len(value) > 50:
            raise ValidationError("Queue name cannot exceed 50 characters.")

        # Check valid characters: a-z, 0-9, _, -
        if not re.match(r"^[a-z0-9_-]+$", value):
            raise ValidationError(
                "Queue name can only contain lowercase letters, numbers, underscores, and hyphens."
            )

        # Check no starting/ending with _ or -
        if value.startswith(("_", "-")) or value.endswith(("_", "-")):
            raise ValidationError(
                "Queue name cannot start or end with underscore or hyphen."
            )

        # Check no consecutive special characters
        if re.search(r"[_-]{2,}", value):
            raise ValidationError(
                "Queue name cannot have repeating underscores or hyphens."
            )

        return value

    files = ListField(
        child=FileField(),
        required=True,
        allow_empty=False,
        error_messages={
            "required": "At least one file must be provided.",
            "empty": "The file list cannot be empty.",
        },
    )

    def validate_files(self, value):
        """Validate the files field."""
        if len(value) == 0:
            raise ValidationError("The file list cannot be empty.")
        if len(value) > self.MAX_FILES_ALLOWED:
            raise ValidationError(f"Maximum '{self.MAX_FILES_ALLOWED}' files allowed.")
        return value

    def validate_llm_profile_id(self, value):
        """Validate that the llm_profile_id belongs to the API key owner."""
        if not value:
            return value

        # Get context from serializer
        api = self.context.get("api")
        api_key = self.context.get("api_key")

        if not api or not api_key:
            raise ValidationError("Unable to validate LLM profile ownership")

        # Check if profile exists
        try:
            profile = ProfileManager.objects.get(profile_id=value)
        except ProfileManager.DoesNotExist:
            raise ValidationError("Profile not found")

        # Get the specific API key being used
        try:
            active_api_key = api.api_keys.get(api_key=api_key, is_active=True)
        except api.api_keys.model.DoesNotExist:
            raise ValidationError("API key not found or not active for this deployment")

        # Check if the profile owner matches the API key owner
        if profile.created_by != active_api_key.created_by:
            raise ValidationError("You can only use profiles that you own")

        return value


class ExecutionQuerySerializer(Serializer):
    execution_id = CharField(required=True)
    include_metadata = BooleanField(default=False)
    include_metrics = BooleanField(default=False)

    def validate_execution_id(self, value):
        """Trim spaces, validate UUID format, and check if execution_id exists."""
        value = value.strip()

        # Validate UUID format
        try:
            uuid_obj = uuid.UUID(value)
        except ValueError:
            raise ValidationError(
                f"Invalid execution_id '{value}'. Must be a valid UUID."
            )

        # Check if UUID exists in the database
        exists = WorkflowExecution.objects.filter(id=uuid_obj).exists()
        if not exists:
            raise ExecutionDoesNotExistError(
                f"Execution with ID '{value}' does not exist."
            )

        return str(uuid_obj)


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
