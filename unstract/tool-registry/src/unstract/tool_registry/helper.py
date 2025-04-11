import logging
from typing import Any

from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.tool_registry.constants import PropKey
from unstract.tool_registry.dto import Tool, ToolMeta
from unstract.tool_registry.exceptions import (
    DuplicateURLException,
    InvalidToolProperties,
    RegistryNotFound,
)
from unstract.tool_registry.tool_utils import ToolUtils
from unstract.tool_sandbox.tool_sandbox import ToolSandbox

logger = logging.getLogger(__name__)


class ToolRegistryHelper:
    def __init__(
        self,
        registry: str,
        private_tools_file: str,
        public_tools_file: str,
        fs: FileStorage = FileStorage(FileStorageProvider.LOCAL),
    ) -> None:
        """Helper class for ToolRegistry.

        Args:
            registry (str): registry.yaml
            private_tools_file (str): private-tools.json
            public_tools_file (str): public-tools.json
            root_dir (str): _description_
        """
        self.registry_file = registry
        self.private_tools_file = private_tools_file
        self.public_tools_file = public_tools_file
        self.fs = fs
        self.tools = self._load_tools_from_registry_file()
        if self.tools:
            logger.info(f"Loaded tools from registry YAML: {self.tools}")

    def _load_tools_from_registry_file(self) -> list[str]:
        """Load all tools from the registry YAML.

        Returns:
            list[str]: _description_
        """
        registry = ToolUtils.get_registry(self.registry_file)
        tools: list[str] = registry.get("tools", [])
        return tools

    def get_tool_unique_id(self, properties: dict[str, Any]) -> str | None:
        """Get Tool uuid Considering function_name as uuid."""
        tool_unique_id: str | None = properties.get(PropKey.FUNCTION_NAME)
        return tool_unique_id

    def get_all_registry_tools(self) -> list[str]:
        """Return loaded registry tool list.

        Returns:
            list[str]: _description_
        """
        return self.tools

    # Next two methods Handling self.tools
    def remove_tool_from_tool_variable(self, registry_tool: str) -> None:
        self.tools.remove(registry_tool)

    def add_tool_to_tool_variable(self, registry_tool: str) -> None:
        self.tools.append(registry_tool)

    # ---------------------------------
    #  Following methods fetch data from source
    # ---------------------------------
    def get_tool_spec(self, tool_meta: ToolMeta) -> dict[str, Any]:
        """get_tool_spec from docker.

        Args:
            tool_meta (ToolMeta): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tool_sandbox = ToolSandbox(
            workflow_id="",
            tool_guid="",
            image_name=tool_meta.image_name,
            image_tag=tool_meta.tag,
        )

        tool_spec: dict[str, Any] | None = tool_sandbox.get_spec()
        if not tool_spec:
            return {}
        return tool_spec

    def get_tool_properties(self, tool_meta: ToolMeta) -> dict[str, Any]:
        """get_tool_properties from docker.

        Args:
            tool_meta (ToolMeta): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tool_sandbox = ToolSandbox(
            workflow_id="",
            tool_guid="",
            image_name=tool_meta.image_name,
            image_tag=tool_meta.tag,
        )

        tool_properties: dict[str, Any] | None = tool_sandbox.get_properties()
        if not tool_properties:
            return {}
        return tool_properties

    def get_tool_icon(self, tool_meta: ToolMeta) -> str:
        """get_tool_icon from docker.

        Args:
            tool_meta (ToolMeta): _description_

        Returns:
            str: _description_
        """
        tool_sandbox = ToolSandbox(
            workflow_id="",
            tool_guid="",
            image_name=tool_meta.image_name,
            image_tag=tool_meta.tag,
        )
        icon: str = tool_sandbox.get_icon()
        if not icon:
            return ""

        return icon

    def get_tool_variables(self, tool_meta: ToolMeta) -> dict[str, Any]:
        """Get variables from docker.

        Args:
            tool_meta (ToolMeta): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tool_sandbox = ToolSandbox(
            workflow_id="",
            tool_guid="",
            image_name=tool_meta.image_name,
            image_tag=tool_meta.tag,
        )

        variables: dict[str, Any] | None = tool_sandbox.get_variables()
        if not variables:
            return {}
        return variables

    def get_tool_data_by_image_url(self, image_url: str) -> Tool:
        """get_tool_data_by_image_url from docker.

        Args:
            image_url (str): _description_

        Raises:
            InvalidToolProperties: _description_

        Returns:
            ToolData: _description_
        """
        tool_metadata = ToolUtils.get_tool_meta_from_tool_url(registry_tool=image_url)
        spec = self.get_tool_spec(tool_meta=tool_metadata)
        properties = self.get_tool_properties(tool_meta=tool_metadata)
        icon = self.get_tool_icon(tool_meta=tool_metadata)
        variables = self.get_tool_variables(tool_meta=tool_metadata)
        tool_unique_id = self.get_tool_unique_id(properties)
        if not tool_unique_id:
            raise InvalidToolProperties(
                f"Tool unique id missed in properties: {image_url}"
            )
        tool = Tool(
            tool_uid=tool_unique_id,
            spec=spec,
            properties=properties,
            variables=variables,
            icon=icon,
            image_url=tool_metadata.tool,
            image_name=tool_metadata.image_name,
            image_tag=tool_metadata.tag,
        )
        return tool

    # ---------------------------------
    # YML Registry Methods
    # ---------------------------------
    def get_registry(self) -> dict[str, Any]:
        """Load the YAML file.

        Raises:
            RegistryNotFound: _description_

        Returns:
            dict[str, Any]: _description_
        """
        yml_data: dict[str, Any] = ToolUtils.get_registry(
            self.registry_file, raise_exc=True
        )
        return yml_data

    def save_registry(self, data: dict[str, Any]) -> None:
        """save_registry Save the updated YAML back to the file.

        Args:
            data (dict[str, Any]): _description_

        Raises:
            RegistryNotFound: _description_
        """
        try:
            ToolUtils.save_registry(self.registry_file, data=data, fs=self.fs)
        except FileNotFoundError:
            logger.error(f"File not found: {self.registry_file}")
            raise RegistryNotFound()

    def remove_tool_from_registry(self, image_url: str) -> None:
        """remove_tool_from_registry.

        Args:
            image_url (_type_): _description_
        """
        registry = self.get_registry()
        registry["tools"].remove(image_url)
        self.save_registry(registry)
        self.remove_tool_from_tool_variable(image_url)

    def add_a_new_tool_to_registry(self, image_url: str) -> None:
        """add_a_new_tool_to_registry.

        Args:
            image_url (_type_): _description_

        Raises:
            DuplicateURLException: _description_
        """
        registry = self.get_registry()
        tools: list[str] = registry.get("tools", [])
        if image_url in tools:
            raise DuplicateURLException(f"Duplicate tool URL: {image_url}")
        registry["tools"].append(image_url)
        self.save_registry(registry)
        self.add_tool_to_tool_variable(image_url)

    # ---------------------------------
    # Tool JSON Methods
    # ---------------------------------

    def load_all_tools_to_disk(self) -> dict[str, Any]:
        """Load all tools json to file.

        Returns:
            dict[str, Any]: _description_
        """
        tools_configs: dict[str, Any] = {}
        for tool in self.tools:
            try:
                logger.info(f"loading tool {tool}")
                tool_data = self.get_tool_data_by_image_url(image_url=tool)
                tools_configs[tool_data.tool_uid] = tool_data.to_json()
            except Exception as error:
                logger.error(f"loading tool {tool} error: {error}")
                continue
        ToolUtils.save_tools_in_to_disk(
            file_path=self.private_tools_file, data=tools_configs
        )
        return tools_configs

    def save_tools(self, data: dict[str, Any]) -> None:
        """Save the updated json back to the file.

        Args:
            data (dict[str, Any]): _description_

        Raises:
            RegistryNotFound: _description_
        """
        try:
            ToolUtils.save_tools_in_to_disk(file_path=self.private_tools_file, data=data)
        except FileNotFoundError:
            logger.error(f"File not found: {self.registry_file}")
            raise RegistryNotFound()

    def get_all_tools_from_disk(self) -> dict[str, dict[str, Any]]:
        """get_all_tools_from_disk.

        Returns:
            dict[str, Any]: _description_
        """
        tool_files = [self.private_tools_file, self.public_tools_file]
        tools = {}
        for tool_file in tool_files:
            try:
                data = ToolUtils.get_all_tools_from_disk(file_path=tool_file, fs=self.fs)
                if not data:
                    logger.info(f"No data from {tool_file}")
                tool_version_list = [
                    f"tool: {k}, version: {v['properties']['toolVersion']}"
                    for k, v in data.items()
                ]
                logger.info(f"Loading tools from {tool_file}: {tool_version_list}")
                tools.update(data)
            except FileNotFoundError:
                logger.warning(f"Unable to find tool file to load tools: {tool_file}")
        return tools

    def get_tool_data_by_id(self, tool_uid: str) -> dict[str, Any]:
        """Get single tool data.

        Args:
            tool_uid (str): _description_

        Returns:
            dict[str, Any]: _description_
        """
        tools: dict[str, Any] = self.get_all_tools_from_disk()
        tool_data: dict[str, Any] = tools.pop(tool_uid, {})
        return tool_data

    def add_new_tool_to_disk_by_uid(self, uuid: str, data: dict[str, Any]) -> None:
        tools = self.get_all_tools_from_disk()
        tools[uuid] = data
        ToolUtils.save_tools_in_to_disk(file_path=self.private_tools_file, data=tools)

    def add_new_tool_to_disk_by_image_url(self, image_url: str) -> None:
        tool_data = self.get_tool_data_by_image_url(image_url=image_url)
        self.add_new_tool_to_disk_by_uid(uuid=tool_data.uid, data=tool_data.data)

    def remove_tools_from_disk(
        self, tools: dict[str, Any], tool_ids: list[str]
    ) -> dict[str, Any]:
        """remove_tools_from_disk.

        Args:
            tools (dict[str, Any]): _description_
            tool_ids (list[str]): _description_

        Returns:
            dict[str, Any]: _description_
        """
        if not tools:
            tools = self.get_all_tools_from_disk()
        for tool_id in tool_ids:
            tools.pop(tool_id, {})
            try:
                ToolUtils.save_tools_in_to_disk(
                    file_path=self.private_tools_file, data=tools
                )
            except FileNotFoundError:
                break
        return tools
