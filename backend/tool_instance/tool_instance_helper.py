import logging
import os
import uuid
from json import JSONDecodeError
from typing import Any, Optional

from account.models import User
from adapter_processor.adapter_processor import AdapterProcessor
from adapter_processor.models import AdapterInstance
from connector.connector_instance_helper import ConnectorInstanceHelper
from jsonschema import ValidationError
from tool_instance.constants import JsonSchemaKey
from tool_instance.models import ToolInstance
from tool_instance.tool_processor import ToolProcessor
from unstract.adapters.enums import AdapterTypes
from unstract.sdk.tool.validator import DefaultsGeneratingValidator
from unstract.tool_registry.constants import AdapterPropertyKey
from unstract.tool_registry.dto import Spec, Tool
from unstract.tool_registry.tool_utils import ToolUtils
from workflow_manager.workflow.constants import WorkflowKey

logger = logging.getLogger(__name__)


class ToolInstanceHelper:
    @staticmethod
    def get_tool_instances_by_workflow(
        workflow_id: str,
        order_by: str,
        lookup: Optional[dict[str, Any]] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[ToolInstance]:
        wf_filter = {}
        if lookup:
            wf_filter = lookup
        wf_filter[WorkflowKey.WF_ID] = workflow_id

        if limit:
            offset_value = 0 if not offset else offset
            to = offset_value + limit
            return list(
                ToolInstance.objects.filter(**wf_filter)[
                    offset_value:to
                ].order_by(order_by)
            )
        return list(
            ToolInstance.objects.filter(**wf_filter).all().order_by(order_by)
        )

    @staticmethod
    def update_instance_metadata(
        org_id: str, tool_instance: ToolInstance, metadata: dict[str, Any]
    ) -> None:
        if (
            JsonSchemaKey.OUTPUT_FILE_CONNECTOR in metadata
            and JsonSchemaKey.OUTPUT_FOLDER in metadata
        ):
            output_connector_name = metadata[
                JsonSchemaKey.OUTPUT_FILE_CONNECTOR
            ]
            output_connector = ConnectorInstanceHelper.get_output_connector_instance_by_name_for_workflow(  # noqa
                tool_instance.workflow_id, output_connector_name
            )
            if output_connector and "path" in output_connector.metadata:
                metadata[JsonSchemaKey.OUTPUT_FOLDER] = os.path.join(
                    output_connector.metadata["path"],
                    *(metadata[JsonSchemaKey.OUTPUT_FOLDER].split("/")),
                )
        if (
            JsonSchemaKey.INPUT_FILE_CONNECTOR in metadata
            and JsonSchemaKey.ROOT_FOLDER in metadata
        ):
            input_connector_name = metadata[JsonSchemaKey.INPUT_FILE_CONNECTOR]
            input_connector = ConnectorInstanceHelper.get_input_connector_instance_by_name_for_workflow(  # noqa
                tool_instance.workflow_id, input_connector_name
            )

            if input_connector and "path" in input_connector.metadata:
                metadata[JsonSchemaKey.ROOT_FOLDER] = os.path.join(
                    input_connector.metadata["path"],
                    *(metadata[JsonSchemaKey.ROOT_FOLDER].split("/")),
                )
        ToolInstanceHelper.update_metadata_with_adapter_instances(
            metadata, tool_instance.tool_id
        )
        metadata[JsonSchemaKey.TENANT_ID] = org_id
        tool_instance.metadata = metadata
        tool_instance.save()

    @staticmethod
    def update_metadata_with_adapter_properties(
        metadata: dict[str, Any],
        adapter_key: str,
        adapter_property: dict[str, Any],
        adapter_type: AdapterTypes,
    ) -> None:
        """Update the metadata dictionary with adapter properties.

        Parameters:
            metadata (dict[str, Any]):
                The metadata dictionary to be updated with adapter properties.
            adapter_key (str):
                The key in the metadata dictionary corresponding to the adapter.
            adapter_property (dict[str, Any]):
                The properties of the adapter.
            adapter_type (AdapterTypes):
                The type of the adapter.

        Returns:
            None
        """
        if adapter_key in metadata:
            adapter_name = metadata[adapter_key]
            adapter = AdapterProcessor.get_adapter_by_name_and_type(
                adapter_type=adapter_type, adapter_name=adapter_name
            )
            adapter_id = str(adapter.id) if adapter else None
            metadata_key_for_id = adapter_property.get(
                AdapterPropertyKey.ADAPTER_ID_KEY, AdapterPropertyKey.ADAPTER_ID
            )
            metadata[metadata_key_for_id] = adapter_id

    @staticmethod
    def update_metadata_with_adapter_instances(
        metadata: dict[str, Any], tool_uid: str
    ) -> None:
        """
        Update the metadata dictionary with adapter instances.
        Parameters:
            metadata (dict[str, Any]):
                The metadata dictionary to be updated with adapter instances.

        Returns:
            None
        """
        tool: Tool = ToolProcessor.get_tool_by_uid(tool_uid=tool_uid)
        schema: Spec = ToolUtils.get_json_schema_for_tool(tool)
        llm_properties = schema.get_llm_adapter_properties()
        embedding_properties = schema.get_embedding_adapter_properties()
        vector_db_properties = schema.get_vector_db_adapter_properties()
        x2text_properties = schema.get_text_extractor_adapter_properties()
        ocr_properties = schema.get_ocr_adapter_properties()

        for adapter_key, adapter_property in llm_properties.items():
            ToolInstanceHelper.update_metadata_with_adapter_properties(
                metadata=metadata,
                adapter_key=adapter_key,
                adapter_property=adapter_property,
                adapter_type=AdapterTypes.LLM,
            )

        for adapter_key, adapter_property in embedding_properties.items():
            ToolInstanceHelper.update_metadata_with_adapter_properties(
                metadata=metadata,
                adapter_key=adapter_key,
                adapter_property=adapter_property,
                adapter_type=AdapterTypes.EMBEDDING,
            )

        for adapter_key, adapter_property in vector_db_properties.items():
            ToolInstanceHelper.update_metadata_with_adapter_properties(
                metadata=metadata,
                adapter_key=adapter_key,
                adapter_property=adapter_property,
                adapter_type=AdapterTypes.VECTOR_DB,
            )

        for adapter_key, adapter_property in x2text_properties.items():
            ToolInstanceHelper.update_metadata_with_adapter_properties(
                metadata=metadata,
                adapter_key=adapter_key,
                adapter_property=adapter_property,
                adapter_type=AdapterTypes.X2TEXT,
            )

        for adapter_key, adapter_property in ocr_properties.items():
            ToolInstanceHelper.update_metadata_with_adapter_properties(
                metadata=metadata,
                adapter_key=adapter_key,
                adapter_property=adapter_property,
                adapter_type=AdapterTypes.OCR,
            )

    # TODO: Review if adding this metadata is still required
    @staticmethod
    def get_altered_metadata(
        tool_instance: ToolInstance,
    ) -> Optional[dict[str, Any]]:
        """Get altered metadata by resolving relative paths.

        This method retrieves the metadata from the given tool instance
        and checks if there are output and input file connectors.
        If output and input file connectors exist in the metadata,
        it resolves the relative paths using connector instances.

        Args:
            tool_instance (ToolInstance).

        Returns:
            Optional[dict[str, Any]]: Altered metadata with resolved relative \
                paths.
        """
        metadata: dict[str, Any] = tool_instance.metadata
        if (
            JsonSchemaKey.OUTPUT_FILE_CONNECTOR in metadata
            and JsonSchemaKey.OUTPUT_FOLDER in metadata
        ):
            output_connector_name = metadata[
                JsonSchemaKey.OUTPUT_FILE_CONNECTOR
            ]
            output_connector = ConnectorInstanceHelper.get_output_connector_instance_by_name_for_workflow(  # noqa
                tool_instance.workflow_id, output_connector_name
            )
            if output_connector and "path" in output_connector.metadata:
                relative_path = ToolInstanceHelper.get_relative_path(
                    metadata[JsonSchemaKey.OUTPUT_FOLDER],
                    output_connector.metadata["path"],
                )
                metadata[JsonSchemaKey.OUTPUT_FOLDER] = relative_path
        if (
            JsonSchemaKey.INPUT_FILE_CONNECTOR in metadata
            and JsonSchemaKey.ROOT_FOLDER in metadata
        ):
            input_connector_name = metadata[JsonSchemaKey.INPUT_FILE_CONNECTOR]
            input_connector = ConnectorInstanceHelper.get_input_connector_instance_by_name_for_workflow(  # noqa
                tool_instance.workflow_id, input_connector_name
            )
            if input_connector and "path" in input_connector.metadata:
                relative_path = ToolInstanceHelper.get_relative_path(
                    metadata[JsonSchemaKey.ROOT_FOLDER],
                    input_connector.metadata["path"],
                )
                metadata[JsonSchemaKey.ROOT_FOLDER] = relative_path
        return metadata

    @staticmethod
    def update_metadata_with_default_adapter(
        adapter_type: AdapterTypes,
        schema_spec: Spec,
        adapter: AdapterInstance,
        metadata: dict[str, Any],
    ) -> None:
        """Update the metadata of a tool instance with default values for
        enabled adapters.

        Parameters:
            adapter_type (AdapterTypes): The type of adapter to update
            the metadata for.
            schema_spec (Spec): The schema specification for the tool.
            adapter (AdapterInstance): The adapter instance to use for updating
            the metadata.
            metadata (dict[str, Any]): The metadata dictionary to update.

        Returns:
            None
        """
        properties = {}
        if adapter_type == AdapterTypes.LLM:
            properties = schema_spec.get_llm_adapter_properties()
        if adapter_type == AdapterTypes.EMBEDDING:
            properties = schema_spec.get_embedding_adapter_properties()
        if adapter_type == AdapterTypes.VECTOR_DB:
            properties = schema_spec.get_vector_db_adapter_properties()
        if adapter_type == AdapterTypes.X2TEXT:
            properties = schema_spec.get_text_extractor_adapter_properties()
        if adapter_type == AdapterTypes.OCR:
            properties = schema_spec.get_ocr_adapter_properties()
        for adapter_key, adapter_property in properties.items():
            metadata_key_for_id = adapter_property.get(
                AdapterPropertyKey.ADAPTER_ID_KEY, AdapterPropertyKey.ADAPTER_ID
            )
            metadata[adapter_key] = adapter.adapter_name
            metadata[metadata_key_for_id] = str(adapter.id)

    @staticmethod
    def update_metadata_with_default_values(
        tool_instance: ToolInstance, user: User
    ) -> None:
        """Update the metadata of a tool instance with default values for
        enabled adapters.

        Parameters:
            tool_instance (ToolInstance): The tool instance to update the
            metadata.

        Returns:
            None
        """
        metadata: dict[str, Any] = tool_instance.metadata
        tool_uuid = tool_instance.tool_id

        tool: Tool = ToolProcessor.get_tool_by_uid(tool_uid=tool_uuid)
        schema: Spec = ToolUtils.get_json_schema_for_tool(tool)

        default_adapters = AdapterProcessor.get_default_adapters(user=user)
        for adapter in default_adapters:
            try:
                adapter_type = AdapterTypes(adapter.adapter_type)
                ToolInstanceHelper.update_metadata_with_default_adapter(
                    adapter_type=adapter_type,
                    schema_spec=schema,
                    adapter=adapter,
                    metadata=metadata,
                )
            except ValueError:
                logger.warning(f"Invalid AdapterType {adapter.adapter_type}")
        tool_instance.metadata = metadata
        tool_instance.save()

    @staticmethod
    def get_relative_path(absolute_path: str, base_path: str) -> str:
        if absolute_path.startswith(base_path):
            relative_path = os.path.relpath(absolute_path, base_path)
        else:
            relative_path = absolute_path
        if relative_path == ".":
            relative_path = ""
        return relative_path

    @staticmethod
    def reorder_tool_instances(instances_to_reorder: list[uuid.UUID]) -> None:
        """Reorders tool instances based on the list of tool UUIDs received.
        Saves the instance in the DB.

        Args:
            instances_to_reorder (list[uuid.UUID]): Desired order of tool UUIDs
        """
        logger.info(f"Reordering instances: {instances_to_reorder}")
        for step, tool_instance_id in enumerate(instances_to_reorder):
            tool_instance = ToolInstance.objects.get(pk=tool_instance_id)
            tool_instance.step = step + 1
            tool_instance.save()

    @staticmethod
    def validate_tool_settings(
        tool_uid: str, tool_meta: dict[str, Any]
    ) -> tuple[bool, str]:
        """Function to validate Tools settings."""

        schema_json: dict[str, Any] = ToolProcessor.get_tool_settings(
            tool_uid=tool_uid
        )
        try:
            DefaultsGeneratingValidator(schema_json).validate(tool_meta)
            return True, ""
        except JSONDecodeError as e:
            return False, str(e)
        except ValidationError as e:
            return False, str(e.schema["description"])
