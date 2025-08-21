import logging
import uuid
from typing import Any

from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from rest_framework.serializers import ListField, Serializer, UUIDField, ValidationError
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.serializers import AuditSerializer
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.constants import ToolKey
from tool_instance_v2.exceptions import ToolDoesNotExist
from tool_instance_v2.models import ToolInstance
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

        # Defensive handling of tool properties and icon
        try:
            rep[ToolKey.ICON] = tool.icon if hasattr(tool, "icon") else ""

            # Handle tool.properties which might be malformed
            if hasattr(tool, "properties") and tool.properties:
                # Check if properties is a list (this might be the bug causing "list indices must be integers")
                if isinstance(tool.properties, list):
                    # If it's a list, try to find display_name in the first dict-like element
                    display_name_found = False
                    for prop in tool.properties:
                        if isinstance(prop, dict):
                            if "display_name" in prop:
                                rep[ToolKey.NAME] = prop["display_name"]
                                display_name_found = True
                                break
                            elif "displayName" in prop:
                                rep[ToolKey.NAME] = prop["displayName"]
                                display_name_found = True
                                break
                    if not display_name_found:
                        rep[ToolKey.NAME] = tool_function
                        logger.warning(
                            f"Tool {tool_function} has list properties but no display_name found, using tool_function as name"
                        )
                elif hasattr(tool.properties, "display_name"):
                    rep[ToolKey.NAME] = tool.properties.display_name
                elif (
                    isinstance(tool.properties, dict)
                    and "display_name" in tool.properties
                ):
                    rep[ToolKey.NAME] = tool.properties["display_name"]
                elif (
                    isinstance(tool.properties, dict) and "displayName" in tool.properties
                ):
                    rep[ToolKey.NAME] = tool.properties["displayName"]
                else:
                    # Fallback: use tool_function as name
                    rep[ToolKey.NAME] = tool_function
                    logger.warning(
                        f"Could not get display_name for tool {tool_function} (properties type: {type(tool.properties)}), using tool_function as name"
                    )
            else:
                rep[ToolKey.NAME] = tool_function
                logger.warning(
                    f"Tool {tool_function} has no properties, using tool_function as name"
                )
        except Exception as e:
            logger.error(f"Error accessing tool properties for {tool_function}: {e}")
            # Use fallback values to prevent serialization errors
            rep[ToolKey.ICON] = ""
            rep[ToolKey.NAME] = tool_function

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
