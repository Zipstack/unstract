import logging
from typing import Any, Optional

from account_v2.models import User
from adapter_processor_v2.adapter_processor import AdapterProcessor
from prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper import (
    PromptStudioRegistryHelper,
)
from tool_instance_v2.exceptions import ToolDoesNotExist
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
        settingsId."""
        tool_registry = ToolRegistry()
        tool: Optional[Tool] = tool_registry.get_tool_by_uid(tool_uid)
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
        ToolProcessor.update_schema_with_adapter_configurations(
            schema=schema, user=user
        )
        schema_json: dict[str, Any] = schema.to_dict()
        return schema_json

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

        if llm_keys:
            adapters = AdapterProcessor.get_adapters_by_type(
                AdapterTypes.LLM, user=user
            )
            for key in llm_keys:
                adapter_names = map(lambda adapter: str(adapter.adapter_name), adapters)
                schema.properties[key]["enum"] = list(adapter_names)

        if embedding_keys:
            adapters = AdapterProcessor.get_adapters_by_type(
                AdapterTypes.EMBEDDING, user=user
            )
            for key in embedding_keys:
                adapter_names = map(lambda adapter: str(adapter.adapter_name), adapters)
                schema.properties[key]["enum"] = list(adapter_names)

        if vector_db_keys:
            adapters = AdapterProcessor.get_adapters_by_type(
                AdapterTypes.VECTOR_DB, user=user
            )
            for key in vector_db_keys:
                adapter_names = map(lambda adapter: str(adapter.adapter_name), adapters)
                schema.properties[key]["enum"] = list(adapter_names)

        if x2text_keys:
            adapters = AdapterProcessor.get_adapters_by_type(
                AdapterTypes.X2TEXT, user=user
            )
            for key in x2text_keys:
                adapter_names = map(lambda adapter: str(adapter.adapter_name), adapters)
                schema.properties[key]["enum"] = list(adapter_names)

        if ocr_keys:
            adapters = AdapterProcessor.get_adapters_by_type(
                AdapterTypes.OCR, user=user
            )
            for key in ocr_keys:
                adapter_names = map(lambda adapter: str(adapter.adapter_name), adapters)
                schema.properties[key]["enum"] = list(adapter_names)

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
        tool_count: int = (
            PromptStudioRegistryHelper.fetch_prompt_studio_tool_count(user)
        )
        return tool_count
