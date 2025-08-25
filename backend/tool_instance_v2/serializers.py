import logging
import uuid
from typing import Any

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.models import AdapterInstance
from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from rest_framework.serializers import ListField, Serializer, UUIDField, ValidationError
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.serializers import AuditSerializer
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.constants import ToolKey
from tool_instance_v2.exceptions import ToolDoesNotExist
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from tool_instance_v2.tool_processor import ToolProcessor
from unstract.sdk.adapters.enums import AdapterTypes
from unstract.tool_registry.dto import Tool
from unstract.tool_registry.tool_utils import ToolUtils

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

        # Transform adapter IDs back to names for UI display
        metadata = rep.get(TIKey.METADATA, {})
        if metadata:
            rep[TIKey.METADATA] = self._transform_adapter_ids_to_names_for_display(
                metadata, tool_function
            )

        return rep

    def _transform_adapter_ids_to_names_for_display(
        self, metadata: dict[str, Any], tool_uid: str
    ) -> dict[str, Any]:
        """Transform adapter IDs back to names for UI display."""
        # Create a copy to avoid mutating the original metadata
        display_metadata = metadata.copy()

        try:
            tool: Tool = ToolProcessor.get_tool_by_uid(tool_uid=tool_uid)
            schema = ToolUtils.get_json_schema_for_tool(tool)

            # Create mapping of adapter keys to their types
            adapter_key_to_type = {}
            for key in schema.get_llm_adapter_properties().keys():
                adapter_key_to_type[key] = AdapterTypes.LLM
            for key in schema.get_embedding_adapter_properties().keys():
                adapter_key_to_type[key] = AdapterTypes.EMBEDDING
            for key in schema.get_vector_db_adapter_properties().keys():
                adapter_key_to_type[key] = AdapterTypes.VECTOR_DB
            for key in schema.get_text_extractor_adapter_properties().keys():
                adapter_key_to_type[key] = AdapterTypes.X2TEXT
            for key in schema.get_ocr_adapter_properties().keys():
                adapter_key_to_type[key] = AdapterTypes.OCR

            # Transform IDs back to names for display
            for adapter_key, adapter_type in adapter_key_to_type.items():
                adapter_value = display_metadata.get(adapter_key)
                if not adapter_value:
                    continue

                # If it's a UUID (adapter ID), convert to name for display
                if ToolInstanceHelper.is_uuid_format(adapter_value):
                    try:
                        adapter_name = AdapterInstance.objects.get(
                            id=adapter_value
                        ).adapter_name
                        if adapter_name:
                            display_metadata[adapter_key] = adapter_name
                        else:
                            # Adapter ID exists but returns None - mark as orphaned
                            display_metadata[adapter_key] = (
                                f"[DELETED ADAPTER: {adapter_value}...]"
                            )
                            logger.warning(
                                f"Adapter ID {adapter_value} references a deleted or inaccessible adapter"
                            )
                    except Exception as e:
                        # If conversion fails, show user-friendly error
                        display_metadata[adapter_key] = f"[{adapter_value}...] NOT FOUND"
                        logger.error(
                            f"Could not resolve adapter ID {adapter_value} to name: {e}"
                        )
                # If it's not a UUID, validate if the adapter name still exists
                elif adapter_value and not ToolInstanceHelper.is_uuid_format(
                    adapter_value
                ):
                    try:
                        # Validate if adapter name still exists
                        adapter = AdapterProcessor.get_adapter_by_name_and_type(
                            adapter_type=adapter_type, adapter_name=adapter_value
                        )
                        if adapter:
                            # Adapter name is valid, display as-is
                            display_metadata[adapter_key] = adapter_value
                        else:
                            # Adapter name no longer exists (likely renamed)
                            display_metadata[adapter_key] = (
                                f"{adapter_value} [NEEDS UPDATE]"
                            )
                            logger.warning(
                                f"Adapter name '{adapter_value}' no longer exists for type {adapter_type} - may have been renamed"
                            )
                    except Exception as e:
                        # If validation fails, show error
                        display_metadata[adapter_key] = f"[{adapter_value} NOT FOUND]"
                        logger.error(
                            f"Could not validate adapter name '{adapter_value}': {e}"
                        )

        except Exception as e:
            logger.error(f"Error transforming adapter IDs to names: {e}", exc_info=True)
        return display_metadata

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
