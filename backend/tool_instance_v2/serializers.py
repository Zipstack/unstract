import logging
import uuid
from typing import Any

from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from rest_framework.serializers import ListField, Serializer, UUIDField, ValidationError
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.constants import RequestKey
from backend.serializers import AuditSerializer
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.constants import ToolKey
from tool_instance_v2.exceptions import ToolDoesNotExist
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from tool_instance_v2.tool_processor import ToolProcessor
from unstract.tool_registry.dto import Tool

logger = logging.getLogger(__name__)


class ToolInstanceSerializer(AuditSerializer):
    workflow_id = UUIDField(write_only=True)

    class Meta:
        model = ToolInstance
        fields = "__all__"
        extra_kwargs = {
            TIKey.WORKFLOW: {
                "required": False,
            },
            TIKey.VERSION: {
                "required": False,
            },
            TIKey.METADATA: {
                "required": False,
            },
            TIKey.STEP: {
                "required": False,
            },
        }

    def to_representation(self, instance: ToolInstance) -> dict[str, str]:
        rep: dict[str, Any] = super().to_representation(instance)
        tool_function = rep.get(TIKey.TOOL_ID)

        if tool_function is None:
            raise ToolDoesNotExist()
        try:
            tool: Tool = ToolProcessor.get_tool_by_uid(tool_function)
        except ToolDoesNotExist:
            return rep
        rep[ToolKey.ICON] = tool.icon
        rep[ToolKey.NAME] = tool.properties.display_name
        # Need to Change it into better method
        if self.context.get(RequestKey.REQUEST):
            metadata = ToolInstanceHelper.get_altered_metadata(instance)
            if metadata:
                rep[TIKey.METADATA] = metadata
        return rep

    def create(self, validated_data: dict[str, Any]) -> Any:
        workflow_id = validated_data.pop(WorkflowKey.WF_ID)
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
        except Workflow.DoesNotExist:
            raise ValidationError(f"Workflow with ID {workflow_id} does not exist.")
        validated_data[TIKey.WORKFLOW] = workflow

        if workflow.tool_instances.count() > 0:
            raise ValidationError(
                f"Workflow with ID {workflow_id} can't have more than one tool."
            )

        tool_uid = validated_data.get(TIKey.TOOL_ID)
        if not tool_uid:
            raise ToolDoesNotExist()

        tool: Tool = ToolProcessor.get_tool_by_uid(tool_uid=tool_uid)
        # TODO: Handle other fields once tools SDK is out
        validated_data[TIKey.PK] = uuid.uuid4()
        # TODO: Use version from tool props
        validated_data[TIKey.VERSION] = ""
        validated_data[TIKey.METADATA] = {
            # TODO: Review and remove tool instance ID
            WorkflowKey.WF_TOOL_INSTANCE_ID: str(validated_data[TIKey.PK]),
            PromptStudioRegistryKeys.PROMPT_REGISTRY_ID: str(tool_uid),
            **ToolProcessor.get_default_settings(tool),
        }
        if TIKey.STEP not in validated_data:
            validated_data[TIKey.STEP] = workflow.tool_instances.count() + 1
        # Workflow will get activated on adding tools to workflow
        if not workflow.is_active:
            workflow.is_active = True
            workflow.save()
        return super().create(validated_data)


class ToolInstanceReorderSerializer(Serializer):
    workflow_id = UUIDField()
    tool_instances = ListField(child=UUIDField())

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        workflow_id = data.get(WorkflowKey.WF_ID)
        tool_instances = data.get(WorkflowKey.WF_TOOL_INSTANCES, [])

        # Check if the workflow exists
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
        except Workflow.DoesNotExist:
            raise ValidationError(f"Workflow with ID {workflow_id} does not exist.")

        # Check if the number of tool instances matches the actual count
        tool_instance_count = workflow.tool_instances.count()
        if len(tool_instances) != tool_instance_count:
            msg = (
                f"Incorrect number of tool instances passed: "
                f"{len(tool_instances)}, expected: {tool_instance_count}"
            )
            logger.error(msg)
            raise ValidationError(detail=msg)

        # Check if each tool instance exists in the workflow
        existing_tool_instance_ids = workflow.tool_instances.values_list("id", flat=True)
        for tool_instance_id in tool_instances:
            if tool_instance_id not in existing_tool_instance_ids:
                raise ValidationError(
                    "One or more tool instances do not exist in the workflow."
                )

        return data
