import logging
from typing import Any

from django.conf import settings
from rest_framework.serializers import (
    CharField,
    ChoiceField,
    JSONField,
    ModelSerializer,
    Serializer,
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
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowSerializer(IntegrityErrorMixin, AuditSerializer):
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
        representation["created_by_email"] = instance.created_by.email
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
            if len(files) > settings.MAX_WORKFLOW_EXECUTION_FILES:
                raise ValidationError({
                    "files": (
                        f"Maximum {settings.MAX_WORKFLOW_EXECUTION_FILES} files are allowed for workflow execution. "
                        f"You have uploaded '{len(files)}' files."
                    )
                })

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
