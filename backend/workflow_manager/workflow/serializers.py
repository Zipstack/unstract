import logging
from typing import Any, Optional, Union

from project.constants import ProjectKey
from rest_framework.serializers import (
    CharField,
    ChoiceField,
    JSONField,
    ModelSerializer,
    Serializer,
    UUIDField,
    ValidationError,
)
from tool_instance.serializers import ToolInstanceSerializer
from tool_instance.tool_instance_helper import ToolInstanceHelper
from workflow_manager.endpoint.models import WorkflowEndpoint
from workflow_manager.workflow.constants import (
    WorkflowExecutionKey,
    WorkflowKey,
)
from workflow_manager.workflow.exceptions import WorkflowGenerationError
from workflow_manager.workflow.generator import WorkflowGenerator
from workflow_manager.workflow.models.workflow import Workflow

from backend.constants import RequestKey
from backend.serializers import AuditSerializer

logger = logging.getLogger(__name__)


class WorkflowSerializer(AuditSerializer):
    tool_instances = ToolInstanceSerializer(many=True, read_only=True)

    class Meta:
        model = Workflow
        fields = "__all__"
        extra_kwargs = {
            WorkflowKey.LLM_RESPONSE: {
                "required": False,
            },
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

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        if validated_data.get(WorkflowKey.PROMPT_TEXT):
            instance.workflow_tool.all().delete()
        return super().update(instance, validated_data)

    def save(self, **kwargs: Any) -> Workflow:
        workflow: Workflow = super().save(**kwargs)
        if self.validated_data.get(WorkflowKey.PROMPT_TEXT):
            try:
                tool_serializer = ToolInstanceSerializer(
                    data=WorkflowGenerator.get_tool_instance_data_from_llm(
                        workflow=workflow
                    ),
                    many=True,
                    context=self.context,
                )
                tool_serializer.is_valid(raise_exception=True)
                tool_serializer.save()
            except Exception as exc:
                logger.error(f"Error while generating tool instances: {exc}")
                raise WorkflowGenerationError

        request = self.context.get("request")
        if not request:
            return workflow
        return workflow


class ExecuteWorkflowSerializer(Serializer):
    workflow_id = UUIDField(required=False)
    project_id = UUIDField(required=False)
    execution_action = ChoiceField(
        choices=Workflow.ExecutionAction.choices, required=False
    )
    execution_id = UUIDField(required=False)
    log_guid = UUIDField(required=False)
    # TODO: Add other fields to handle WFExecution method, mode .etc.

    def get_workflow_id(
        self, validated_data: dict[str, Union[str, None]]
    ) -> Optional[str]:
        return validated_data.get(WorkflowKey.WF_ID)

    def get_project_id(
        self, validated_data: dict[str, Union[str, None]]
    ) -> Optional[str]:
        return validated_data.get(ProjectKey.PROJECT_ID)

    def get_execution_id(
        self, validated_data: dict[str, Union[str, None]]
    ) -> Optional[str]:
        return validated_data.get(WorkflowExecutionKey.EXECUTION_ID)

    def get_log_guid(
        self, validated_data: dict[str, Union[str, None]]
    ) -> Optional[str]:
        return validated_data.get(WorkflowExecutionKey.LOG_GUID)

    def get_execution_action(
        self, validated_data: dict[str, Union[str, None]]
    ) -> Optional[str]:
        return validated_data.get(WorkflowKey.EXECUTION_ACTION)

    def validate(
        self, data: dict[str, Union[str, None]]
    ) -> dict[str, Union[str, None]]:
        workflow_id = data.get(WorkflowKey.WF_ID)
        project_id = data.get(ProjectKey.PROJECT_ID)

        if not workflow_id and not project_id:
            raise ValidationError(
                "At least one of 'workflow_id' or 'project_id' is required."
            )

        return data


class ExecuteWorkflowResponseSerializer(Serializer):
    workflow_id = UUIDField()
    execution_id = UUIDField()
    execution_status = CharField()
    log_id = CharField()
    error = CharField()
    result = JSONField()


class WorkflowEndpointSerializer(ModelSerializer):
    workflow_name = CharField(source="workflow.workflow_name", read_only=True)

    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"
