import logging
import os
from typing import Any, Optional

from unstract.tool_registry.constants import PropKey, ToolJsonField, ToolKey
from unstract.tool_registry.dto import Tool
from unstract.tool_registry.exceptions import InvalidToolURLException
from unstract.tool_registry.helper import ToolRegistryHelper
from unstract.tool_registry.schema_validator import JsonSchemaValidator
from unstract.tool_registry.tool_utils import ToolUtils

logger = logging.getLogger(__name__)


class ToolRegistry:
    REGISTRY_FILE = "registry.yaml"
    PRIVATE_TOOL_CONFIG_FILE = "private_tools.json"
    PUBLIC_TOOL_CONFIG_FILE = "public_tools.json"

    def __init__(
        self,
        private_tools: str = PRIVATE_TOOL_CONFIG_FILE,
        public_tools: str = PUBLIC_TOOL_CONFIG_FILE,
        registry_file: str = REGISTRY_FILE,
    ) -> None:
        """ToolRegistry class for managing activated tools listed in the Tools
        Registry.

        The ToolRegistry class provides methods to interact with various tools
        that are listed in the registry.yaml file. It serves as a central hub
        for accessing and utilizing these tools within an application.

        Methods:
            - add_new_tool_by_image_url(image_url): Add a new tool in registry.
            - remove_tool_by_uid(tool_id): Remove a Tool from registry.
            - list_tools_urls(): List all tools URLs available in the registry.
            - get_available_tools(): List all tools available in the registry.
            - get_tool_spec_by_tool_id(): Get json schema/ Spec of a tool.
            - get_tool_properties_by_tool_id(): Get properties of a tool.
            - get_tool_icon__by_tool_id(): Get icon of a tool.
        """
        directory = os.getenv("TOOL_REGISTRY_CONFIG_PATH")
        if not directory:
            raise ValueError(
                "Env 'TOOL_REGISTRY_CONFIG_PATH' is not set, please add the tool "
                "registry JSONs and YAML to a directory and set the env."
            )
        self.helper = ToolRegistryHelper(
            registry=os.path.join(directory, registry_file),
            private_tools_file=os.path.join(directory, private_tools),
            public_tools_file=os.path.join(directory, public_tools),
        )

    def load_all_tools_to_disk(self) -> None:
        self.helper.load_all_tools_to_disk()

    def add_new_tool_by_image_url(self, image_url: str) -> None:
        """add_new_tool_by_image_url.

        Args:
            image_url (str): _description_

        Raises:
            InvalidToolURLException: _description_
        """
        if not ToolUtils.is_valid_tool_url(image_url=image_url):
            raise InvalidToolURLException(f"Invalid tool URL: {image_url}")

        self.helper.add_a_new_tool_to_registry(image_url=image_url)
        self.helper.add_new_tool_to_disk_by_image_url(image_url=image_url)

    def remove_tool_by_uid(self, tool_id: str) -> None:
        """remove_tool_by_uid.

        Args:
            tool_id (str): tool unique id
        """
        try:
            tools: dict[str, Any] = self.helper.get_all_tools_from_disk()
            tool_data: dict[str, Any] = tools.pop(tool_id, {})
            if not tool_data:
                logger.warning(f"Tool '{tool_id}' not found in the JSON file.")
                return
            image_url: str = tool_data.get("image_url", "")

            self.helper.remove_tool_from_registry(image_url=image_url)
            logger.info(f"Tool '{tool_id}' removed from registry successfully.")
            self.helper.save_tools(data=tools)
            logger.info(f"Tool '{tool_id}' removed from tools file successfully.")
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")

    def list_tools_urls(self) -> list[str]:
        """List all the tools available in the registry."""
        tools: list[str] = self.helper.get_all_registry_tools()
        return tools

    def fetch_all_tools(self, filter: list[str] = []) -> list[Tool]:
        """Get all tools from json with optional filter.

        Args:
            filter (list[str], optional): filter. Defaults to [].

        Returns:
            list[dict[str, Any]]: Tools
        """
        tools_list: list[Tool] = []
        tools = self.helper.get_all_tools_from_disk()
        for tool_uid, data in tools.items():
            properties = data.get(ToolJsonField.PROPERTIES)
            spec = data.get(ToolJsonField.SPEC)
            if not properties and not spec:
                continue
            tool_data = Tool.from_dict(tool_uid, data)
            tools_list.append(tool_data)
        return tools_list

    def get_tool_by_uid(self, uid: str) -> Optional[Tool]:
        """Get tools from json.

        Args:
            uid (str): Tool Uid.

        Returns:
            list[dict[str, Any]]: Tools
        """
        tools = self.helper.get_all_tools_from_disk()
        data = tools.get(uid)
        if not data:
            return None
        properties = data.get(ToolJsonField.PROPERTIES)
        spec = data.get(ToolJsonField.SPEC)
        if not properties and not spec:
            return None
        tool_data = Tool.from_dict(uid, data)
        return tool_data

    def fetch_tools_descriptions(
        self, load_from_source: bool = False
    ) -> list[dict[str, Any]]:
        """Get all available tools with specific fields.

        Result will be in a format with the fields
        - name
        - description
        - function_name
        - output_type
        - input_type
        - icon

        Args:
            load_from_source (bool, optional): _description_. Defaults to False.

        Returns:
            list[dict[str, Any]]: _description_
        """
        tools_list = []
        if load_from_source:
            for tool in self.helper.get_all_registry_tools():
                tool_meta = ToolUtils.get_tool_meta_from_tool_url(registry_tool=tool)
                if not tool_meta:
                    continue
                properties = self.helper.get_tool_properties(tool_meta=tool_meta)
                icon = self.helper.get_tool_icon(tool_meta=tool_meta)
                if not properties:
                    continue
                tool_data = {
                    ToolKey.NAME: properties.get(PropKey.DISPLAY_NAME),
                    ToolKey.DESCRIPTION: properties.get(PropKey.DESCRIPTION),
                    ToolKey.ICON: icon,
                    ToolKey.FUNCTION_NAME: properties.get(PropKey.FUNCTION_NAME),
                }
                tools_list.append(tool_data)
        else:
            tools = self.helper.get_all_tools_from_disk()
            for tool, configuration in tools.items():
                data: Optional[dict[str, Any]] = configuration.get("properties")
                icon = configuration.get("icon", "")
                if not data:
                    continue
                tool_data = {
                    ToolKey.NAME: data.get(PropKey.DISPLAY_NAME),
                    ToolKey.DESCRIPTION: data.get(PropKey.DESCRIPTION),
                    ToolKey.ICON: icon,
                    ToolKey.FUNCTION_NAME: data.get(PropKey.FUNCTION_NAME),
                }
                tools_list.append(tool_data)
        return tools_list

    def get_available_tools(
        self, tool_uids: list[str] = [], load_from_source: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Get all available tools from the tool registry.

        Args:
            load_from_source (bool, optional): load from container.
                Defaults to False. If False, it will load from the JSON file
            tool_uids: list of tool IDs to fetch

        Returns:
            dict[str, Any]: tools
        """
        tools_list = {}
        if load_from_source:
            for tool in self.helper.get_all_registry_tools():
                tool_meta = ToolUtils.get_tool_meta_from_tool_url(registry_tool=tool)
                if not tool_meta:
                    continue
                properties: Optional[dict[str, Any]] = self.helper.get_tool_properties(
                    tool_meta=tool_meta
                )
                spec: Optional[dict[str, Any]] = self.helper.get_tool_spec(
                    tool_meta=tool_meta
                )
                icon = self.helper.get_tool_icon(tool_meta=tool_meta)
                if not properties or not spec:
                    continue

                tool_uid = self.helper.get_tool_unique_id(properties)
                if not tool_uid:
                    continue

                if tool_uid in tool_uids:
                    tools_list[tool_uid] = {
                        "image_name": tool_meta.image_name,
                        "image_tag": tool_meta.tag,
                        "image_url": tool_meta.tool,
                        "spec": spec,
                        "properties": properties,
                        "icon": icon,
                    }
        else:
            tools: dict[str, dict[str, Any]] = self.helper.get_all_tools_from_disk()
            for tool, configuration in tools.items():
                properties = configuration.get("properties")
                spec = configuration.get("spec")
                icon = configuration.get("icon", "")
                image_url = configuration.get("image_url", "")
                image_name = configuration.get("image_name")
                image_tag = configuration.get("image_tag", "")
                if not (properties and spec and image_name):
                    logger.warning(f"missing params in {tool}")
                    continue

                tool_uid = self.helper.get_tool_unique_id(properties)
                if not tool_uid:
                    continue

                if tool_uid in tool_uids:
                    tools_list[tool_uid] = {
                        "image_name": image_name,
                        "image_tag": image_tag,
                        "image_url": image_url,
                        "spec": spec,
                        "properties": properties,
                        "icon": icon,
                    }
        return tools_list

    def get_tool_spec_by_tool_id(self, tool_id: str) -> dict[str, Any]:
        """Get Tool Spec.

        Args:
            tool_id (str): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tools = self.helper.get_all_tools_from_disk()
        spec: dict[str, Any] = tools.get(tool_id, {}).get("spec", {})
        return spec

    def get_tool_properties_by_tool_id(self, tool_id: str) -> dict[str, Any]:
        """Get tool properties.

        Args:
            tool_id (str): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tools = self.helper.get_all_tools_from_disk()
        properties: dict[str, Any] = tools.get(tool_id, {}).get("properties", {})
        return properties

    def get_tool_icon_by_tool_id(self, tool_id: str) -> dict[str, Any]:
        """Get tool icon using tool uid.

        Args:
            tool_id (str): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tools = self.helper.get_all_tools_from_disk()
        icon: dict[str, Any] = tools.get(tool_id, {}).get("icon", {})
        return icon

    def is_image_available(self, tool_id: str) -> bool:
        """Check the availability of container.

        Args:
            tool_id (str): Tool uid

        Returns:
            bool: status
        """
        tool = self.helper.get_tool_data_by_id(tool_uid=tool_id)
        image_url = tool.get("image_url")
        status = False
        if image_url:
            status = self.helper.is_image_ready(image_name=image_url)
        return status

    def is_image_ready(self, image_name: str) -> bool:
        """Check the availability of container.

        Args:
            tool_id (str): Tool uid

        Returns:
            bool: status
        """
        is_ready: bool = self.helper.is_image_ready(image_name=image_name)
        return is_ready

    def validate_schema_with_data(
        self, schema: dict[str, Any], data: dict[str, Any]
    ) -> None:
        """Validate input data with JsonSchema.

        Returns:
            dict[str, Any]: _description_
        """
        validator = JsonSchemaValidator(schema=schema)
        validator.validate_data(data=data)
