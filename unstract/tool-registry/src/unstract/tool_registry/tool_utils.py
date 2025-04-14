import json
import logging
import re
from typing import Any

from unstract.sdk.adapters.enums import AdapterTypes
from unstract.sdk.file_storage import FileStorage, FileStorageProvider
from unstract.tool_registry.constants import AdapterPropertyKey, Tools
from unstract.tool_registry.dto import AdapterProperties, Spec, Tool, ToolMeta
from unstract.tool_registry.exceptions import InvalidToolURLException, RegistryNotFound

logger = logging.getLogger(__name__)


class ToolUtils:
    TOOLS_FILE = ""

    @staticmethod
    def is_valid_tool_url(image_url: str) -> bool:
        # Define a regular expression pattern for Docker image URLs
        docker_pattern = r"^docker:[a-zA-Z0-9_.-]+(/[a-zA-Z0-9_.-]+)*/[a-zA-Z0-9_.-]+$"

        # Define a regular expression pattern for local tool URLs
        local_pattern = r"^local:[a-zA-Z0-9_.-:]+$"

        # Check if the URL matches either the Docker image or local tool pattern
        if re.match(docker_pattern, image_url) or re.match(local_pattern, image_url):
            return True
        else:
            return False

    @staticmethod
    def get_tool_meta_from_tool_url(registry_tool: str) -> ToolMeta:
        parts = registry_tool.split(":")
        if len(parts) < 2:
            raise InvalidToolURLException(f"Invalid tool URL: {registry_tool}")
        tool_type, tool_path = parts[0], parts[1]

        image_tag = Tools.IMAGE_LATEST_TAG
        if len(parts) == 3:
            image_tag = parts[2]
        image_name = tool_path
        if tool_path.startswith("/"):
            image_name = tool_path.rsplit("/", 1)[1]
        image_name_with_tag = f"{image_name}:{image_tag}"
        if not (tool_type and tool_path and image_name and image_name_with_tag):
            raise InvalidToolURLException(f"Invalid tool URL: {registry_tool}")
        return ToolMeta(
            tool=registry_tool,
            tool_type=tool_type,
            tool_path=tool_path,
            image_name_with_tag=image_name_with_tag,
            tag=image_tag,
            image_name=image_name,
        )

    @staticmethod
    def save_tools_in_to_disk(
        file_path: str,
        data: dict[str, Any],
        fs: FileStorage = FileStorage(FileStorageProvider.LOCAL),
    ) -> None:
        fs.json_dump(path=file_path, mode="w", encoding="utf-8", data=data)

    @staticmethod
    def get_all_tools_from_disk(
        file_path: str, fs: FileStorage = FileStorage(FileStorageProvider.LOCAL)
    ) -> dict[str, Any]:
        try:
            data = fs.json_load(file_path)
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Error loading tools from {file_path}: {e}")
            return {}

    @staticmethod
    def save_registry(
        file_path: str,
        data: dict[str, Any],
        fs: FileStorage = FileStorage(FileStorageProvider.LOCAL),
    ) -> None:
        fs.yaml_dump(path=file_path, mode="w", encoding="utf-8", data=data)

    @staticmethod
    def get_registry(
        file_path: str,
        fs: FileStorage = FileStorage(FileStorageProvider.LOCAL),
        raise_exc: bool = False,
    ) -> dict[str, Any]:
        """Get Registry File.

        Args:
            file_path (str): file path of registry.yaml
            fs (FileStorage): file storage to be used

        Returns:
            dict[str, Any]: yaml data
        """
        yml_data: dict[str, Any] = {}
        try:
            logger.debug(f"Reading tool registry YAML: {file_path}")
            yml_data = fs.yaml_load(file_path)

        except FileNotFoundError:
            logger.warning(f"Could not find tool registry YAML: {str(file_path)}")
            if raise_exc:
                raise RegistryNotFound()
        except Exception as error:
            logger.error(f"Error while loading {str(file_path)}: {error}")
            if raise_exc:
                raise error
        return yml_data

    @staticmethod
    def create_image_name(image_name: str, tag: str | None) -> str:
        if tag is not None:
            image_name_with_tag = f"{image_name}:{tag}"
            return image_name_with_tag
        else:
            # Handle the case when tag is None
            return image_name

    @staticmethod
    def get_default_settings(tool: Tool) -> dict[str, str]:
        specs = {}
        spec_props = tool.spec.properties
        for prop in spec_props:
            if "default" in spec_props[prop]:
                specs[prop] = spec_props[prop]["default"]
            else:
                if spec_props[prop]["type"] == "string":
                    specs[prop] = ""
                elif spec_props[prop]["type"] == "integer":
                    specs[prop] = 0
                elif spec_props[prop]["type"] == "boolean":
                    specs[prop] = False
                elif spec_props[prop]["type"] == "array":
                    specs[prop] = []
                elif spec_props[prop]["type"] == "object":
                    specs[prop] = {}
                else:
                    specs[prop] = None
        return specs

    @staticmethod
    def get_adapter_schema(
        type: AdapterTypes,
        adapter_id_key: str,
        title: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Get the schema for an adapter.

        Args:
            type (AdapterTypes): The type of the adapter.
            adapter_id_key (str): The key for the adapter ID.
            title (str, optional): The title of the adapter. Defaults to "".
            description (str, optional): The description of the adapter.
                Defaults to "".

        Returns:
            dict[str, Any]: The schema for the adapter.
        """
        schema = {
            "adapterType": type.value,
            "type": "string",
            "title": title,
            "description": description,
            "enum": [],
        }
        schema[AdapterPropertyKey.ADAPTER_ID_KEY] = adapter_id_key
        return schema

    @staticmethod
    def get_enabled_adapters(
        adapters: list[AdapterProperties],
    ) -> list[AdapterProperties]:
        """Filter and return a list of enabled adapters.

        Args:
            adapters (list[AdapterProperties]):
                A list of AdapterProperties objects representing the adapters.

        Returns:
            list[AdapterProperties]:
                A list of enabled AdapterProperties objects.
        """
        enabled_adapters = [adapter for adapter in adapters if adapter.is_enabled]
        return enabled_adapters

    @staticmethod
    def process_adapter_models(
        models: list[AdapterProperties],
        adapter_type: AdapterTypes,
        schema: Spec,
        default_adapter_id: str | None = None,
    ) -> None:
        """Process adapter models and update the schema.

        This method processes the adapter models and updates the
        tool spec schema accordingly.

        Args:
            models (list[AdapterProperties]): A list of adapter models.
            adapter_type (AdapterTypes): The type of the adapter.
            schema (Spec): The tool spec schema.
            default_adapter_id (Optional[str], optional):
                The default adapter ID. Defaults to None.

        Returns:
            None

        Raises:
            None
        """
        for index, model in enumerate(models, start=1):
            title = model.title
            description = model.description
            is_required = model.is_required
            adapter_id_key = model.adapter_id
            if default_adapter_id and not adapter_id_key:
                adapter_id_key = default_adapter_id
            if not adapter_id_key:
                continue
            key = adapter_type.value + "-" + str(index)
            schema.properties[key] = ToolUtils.get_adapter_schema(
                type=adapter_type,
                title=title,
                description=description,
                adapter_id_key=adapter_id_key,
            )
            if is_required:
                schema.required.append(key)

    @staticmethod
    def get_json_schema_for_tool(tool: Tool) -> Any:
        """Get the JSON schema for a tool.

        This method takes a `Tool` object as input and generates a JSON schema
        based on the tool's specifications and enabled adapters.
        The generated schema can be used for validation and configuration
        purposes.

        Parameters:
            tool (Tool):
                The `Tool` object for which to generate the JSON schema.

        Returns:
            Any: The generated JSON schema.
        """
        schema = tool.spec
        adapter = tool.properties.adapter

        language_models = ToolUtils.get_enabled_adapters(adapter.language_models)
        embeddings = ToolUtils.get_enabled_adapters(adapter.embedding_services)
        vector_stores = ToolUtils.get_enabled_adapters(adapter.vector_stores)
        text_extractors = ToolUtils.get_enabled_adapters(adapter.text_extractors)
        ocrs = ToolUtils.get_enabled_adapters(adapter.ocrs)

        ToolUtils.process_adapter_models(
            models=language_models,
            adapter_type=AdapterTypes.LLM,
            schema=schema,
            default_adapter_id=AdapterPropertyKey.DEFAULT_LLM_ADAPTER_ID,
        )
        ToolUtils.process_adapter_models(
            models=embeddings,
            adapter_type=AdapterTypes.EMBEDDING,
            schema=schema,
            default_adapter_id=AdapterPropertyKey.DEFAULT_EMBEDDING_ADAPTER_ID,
        )
        ToolUtils.process_adapter_models(
            models=vector_stores,
            adapter_type=AdapterTypes.VECTOR_DB,
            schema=schema,
            default_adapter_id=AdapterPropertyKey.DEFAULT_VECTOR_DB_ADAPTER_ID,
        )
        ToolUtils.process_adapter_models(
            models=text_extractors,
            adapter_type=AdapterTypes.X2TEXT,
            schema=schema,
            default_adapter_id=AdapterPropertyKey.DEFAULT_X2TEXT_ADAPTER_ID,
        )
        ToolUtils.process_adapter_models(
            models=ocrs,
            adapter_type=AdapterTypes.OCR,
            schema=schema,
            default_adapter_id=AdapterPropertyKey.DEFAULT_OCR_ADAPTER_ID,
        )
        return schema
