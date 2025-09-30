import logging
import uuid
from typing import Any

from account_v2.models import User
from adapter_processor_v2.adapter_processor import AdapterProcessor
from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
from prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper import (
    PromptStudioRegistryHelper,
)

from tool_instance_v2.exceptions import ToolDoesNotExist
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import AdapterTypes
else:
    from unstract.sdk.adapters.enums import AdapterTypes

from unstract.tool_registry.dto import Spec, Tool
from unstract.tool_registry.tool_registry import ToolRegistry
from unstract.tool_registry.tool_utils import ToolUtils

logger = logging.getLogger(__name__)


class ToolProcessor:
    TOOL_NOT_IN_REGISTRY_MESSAGE = "Tool does not exist in registry"

    @staticmethod
    def get_tool_by_uid(tool_uid: str) -> Tool:
        """Function to get and instantiate a tool for a given tool
        settingsId.
        """
        tool_registry = ToolRegistry()
        tool: Tool | None = tool_registry.get_tool_by_uid(tool_uid)
        # HACK: Assume tool_uid is prompt_registry_id for fetching a dynamic
        # tool made with Prompt Studio.
        if not tool:
            tool = PromptStudioRegistryHelper.get_tool_by_prompt_registry_id(
                prompt_registry_id=tool_uid
            )
        if not tool:
            raise ToolDoesNotExist(
                f"{ToolProcessor.TOOL_NOT_IN_REGISTRY_MESSAGE}: {tool_uid}"
            )
        return tool

    @staticmethod
    def get_default_settings(tool: Tool) -> dict[str, str]:
        """Function to make and fill settings with default values.

        Args:
            tool (ToolSettings): tool

        Returns:
            dict[str, str]: tool settings
        """
        tool_metadata: dict[str, str] = ToolUtils.get_default_settings(tool)
        return tool_metadata

    @staticmethod
    def get_json_schema_for_tool(tool_uid: str, user: User) -> dict[str, str]:
        """Function to Get JSON Schema for Tools."""
        tool: Tool = ToolProcessor.get_tool_by_uid(tool_uid=tool_uid)
        schema: Spec = ToolUtils.get_json_schema_for_tool(tool)
        ToolProcessor.update_schema_with_adapter_configurations(schema=schema, user=user)
        schema_json: dict[str, Any] = schema.to_dict()
        return schema_json

    @staticmethod
    def _update_schema_for_adapter_type(
        schema: Spec, keys: list[str], adapter_type: AdapterTypes, user: User
    ) -> None:
        """Helper method to update schema properties for a specific adapter type."""
        if not keys:
            return

        adapters = AdapterProcessor.get_adapters_by_type(adapter_type, user=user)
        adapter_ids = [str(adapter.id) for adapter in adapters]
        adapter_names = [adapter.adapter_name for adapter in adapters]

        for key in keys:
            schema.properties[key]["enum"] = adapter_ids
            schema.properties[key]["enumNames"] = adapter_names

    @staticmethod
    def update_schema_with_adapter_configurations(schema: Spec, user: User) -> None:
        """Updates the JSON schema with the available adapter configurations
        for the LLM, embedding, and vector DB adapters.

        Args:
            schema (Spec): The JSON schema object to be updated.

        Returns:
            None. The `schema` object is updated in-place.
        """
        llm_keys = schema.get_llm_adapter_properties_keys()
        embedding_keys = schema.get_embedding_adapter_properties_keys()
        vector_db_keys = schema.get_vector_db_adapter_properties_keys()
        x2text_keys = schema.get_text_extractor_adapter_properties_keys()
        ocr_keys = schema.get_ocr_adapter_properties_keys()

        ToolProcessor._update_schema_for_adapter_type(
            schema, llm_keys, AdapterTypes.LLM, user
        )
        ToolProcessor._update_schema_for_adapter_type(
            schema, embedding_keys, AdapterTypes.EMBEDDING, user
        )
        ToolProcessor._update_schema_for_adapter_type(
            schema, vector_db_keys, AdapterTypes.VECTOR_DB, user
        )
        ToolProcessor._update_schema_for_adapter_type(
            schema, x2text_keys, AdapterTypes.X2TEXT, user
        )
        ToolProcessor._update_schema_for_adapter_type(
            schema, ocr_keys, AdapterTypes.OCR, user
        )

    @staticmethod
    def get_tool_list(user: User) -> list[dict[str, Any]]:
        """Function to get a list of tools."""
        tool_registry = ToolRegistry()
        prompt_studio_tools: list[dict[str, Any]] = (
            PromptStudioRegistryHelper.fetch_json_for_registry(user)
        )
        tool_list: list[dict[str, Any]] = tool_registry.fetch_tools_descriptions()
        tool_list = tool_list + prompt_studio_tools
        return tool_list

    @staticmethod
    def get_prompt_studio_tool_count(user: User) -> int:
        """Get count of valid prompt studio tools."""
        # Filter the Prompt studio registry based on the users.
        prompt_studio_tools = PromptStudioRegistry.objects.list_tools(user)
        valid_tools = 0

        for tool in prompt_studio_tools:
            try:
                uuid.UUID(str(tool.prompt_registry_id))
                valid_tools += 1
            except ValueError:
                continue

        return valid_tools
