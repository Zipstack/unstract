import logging
from typing import Any

from django.conf import settings
from permissions.co_owner_serializers import CoOwnerRepresentationMixin
from rest_framework.serializers import (
    CharField,
    ChoiceField,
    JSONField,
    ModelSerializer,
    Serializer,
    SerializerMethodField,
    UUIDField,
    ValidationError,
)
from tool_instance_v2.serializers import ToolInstanceSerializer
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin

from backend.constants import RequestKey
from backend.serializers import AuditSerializer
from workflow_manager.workflow_v2.constants import WorkflowExecutionKey, WorkflowKey
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowSerializer(
    CoOwnerRepresentationMixin, IntegrityErrorMixin, AuditSerializer
):
    tool_instances = ToolInstanceSerializer(many=True, read_only=True)

    class Meta:
        model = Workflow
        fields = "__all__"
        extra_kwargs = {
            WorkflowKey.LLM_RESPONSE: {
                "required": False,
            },
        }

    unique_error_message_map: dict[str, dict[str, str]] = {
        "unique_workflow_name": {
            "field": "workflow_name",
            "message": "A workflow with this name already exists.",
        }
    }

    def to_representation(self, instance: Workflow) -> dict[str, str]:
        representation: dict[str, str] = super().to_representation(instance)
        representation[WorkflowKey.WF_NAME] = instance.workflow_name
        representation[WorkflowKey.WF_TOOL_INSTANCES] = ToolInstanceSerializer(
            ToolInstanceHelper.get_tool_instances_by_workflow(
                workflow_id=instance.id, order_by="step"
            ),
            many=True,
            context=self.context,
        ).data
        request = self.context.get("request")
        self.add_co_owner_fields(instance, representation, request)
        return representation

    def create(self, validated_data: dict[str, Any]) -> Any:
        if self.context.get(RequestKey.REQUEST):
            validated_data[WorkflowKey.WF_OWNER] = self.context.get(
                RequestKey.REQUEST
            ).user
        return super().create(validated_data)


class ExecuteWorkflowSerializer(Serializer):
    workflow_id = UUIDField(required=True)
    execution_action = ChoiceField(
        choices=Workflow.ExecutionAction.choices, required=False
    )
    execution_id = UUIDField(required=False)
    log_guid = UUIDField(required=False)
    # TODO: Add other fields to handle WFExecution method, mode .etc.

    def get_workflow_id(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(WorkflowKey.WF_ID)

    def get_execution_id(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(WorkflowExecutionKey.EXECUTION_ID)

    def get_log_guid(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(WorkflowExecutionKey.LOG_GUID)

    def get_execution_action(self, validated_data: dict[str, str | None]) -> str | None:
        return validated_data.get(WorkflowKey.EXECUTION_ACTION)

    def validate(self, data: dict[str, str | None]) -> dict[str, str | None]:
        # Validate file count from request context
        request = self.context.get(RequestKey.REQUEST)
        if request and hasattr(request, "FILES"):
            files = request.FILES.getlist("files")
            if len(files) > settings.WORKFLOW_PAGE_MAX_FILES:
                raise ValidationError(
                    {
                        "files": (
                            f"Maximum {settings.WORKFLOW_PAGE_MAX_FILES} files are allowed for workflow execution. "
                            f"You have uploaded '{len(files)}' files."
                        )
                    },
                    code="max_file_limit_exceeded",
                )

        return data


class ExecuteWorkflowResponseSerializer(Serializer):
    workflow_id = UUIDField()
    execution_id = UUIDField()
    execution_status = CharField()
    log_id = CharField()
    error = CharField()
    result = JSONField()


class WorkflowExecutionSerializer(ModelSerializer):
    class Meta:
        model = WorkflowExecution
        fields = "__all__"


class WorkflowExecutionLogSerializer(ModelSerializer):
    class Meta:
        model = ExecutionLog
        fields = "__all__"


class FileHistorySerializer(ModelSerializer):
    max_execution_count = SerializerMethodField()
    has_exceeded_limit = SerializerMethodField()

    class Meta:
        model = FileHistory
        fields = "__all__"

    def get_max_execution_count(self, obj: FileHistory) -> int:
        """Get the maximum execution count from the associated workflow.

        Args:
            obj: FileHistory instance

        Returns:
            int: Maximum execution count from workflow configuration
        """
        return obj.workflow.get_max_execution_count()

    def get_has_exceeded_limit(self, obj: FileHistory) -> bool:
        """Check if this file has exceeded its execution limit.

        Args:
            obj: FileHistory instance

        Returns:
            bool: True if file has exceeded limit and should be skipped
        """
        return obj.has_exceeded_limit(obj.workflow)


class SharedUserListSerializer(ModelSerializer):
    """Serializer for returning workflow with shared user details."""

    shared_users = SerializerMethodField()
    co_owners = SerializerMethodField()
    created_by = SerializerMethodField()

    class Meta:
        model = Workflow
        fields = [
            "id",
            "workflow_name",
            "shared_users",
            "co_owners",
            "shared_to_org",
            "created_by",
        ]

    def get_shared_users(self, obj):
        """Return list of shared users with id and email."""
        return [{"id": user.id, "email": user.email} for user in obj.shared_users.all()]

    def get_co_owners(self, obj):
        """Return list of co-owners with id and email."""
        return [{"id": user.id, "email": user.email} for user in obj.co_owners.all()]

    def get_created_by(self, obj):
        """Return creator details."""
        if obj.created_by:
            return {"id": obj.created_by.id, "email": obj.created_by.email}
        return None
