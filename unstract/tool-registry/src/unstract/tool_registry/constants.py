from typing import Any


class Tools:
    TOOLS_DIRECTORY = "tools"
    IMAGE_LATEST_TAG = "latest"


class Command:
    SPEC = "SPEC"
    PROPERTIES = "PROPERTIES"
    ICON = "ICON"
    RUN = "RUN"
    VARIABLES = "VARIABLES"


class ToolJsonField:
    PROPERTIES = "properties"
    SPEC = "spec"
    VARIABLES = "variables"
    ICON = "icon"
    IMAGE_URL = "image_url"
    IMAGE_NAME = "image_name"
    IMAGE_TAG = "image_tag"

    @classmethod
    def get_values(cls) -> list[str]:
        variable_values = [
            value for value in vars(cls).values() if isinstance(value, str)
        ]
        return variable_values


class ToolKey:
    NAME = "name"
    DESCRIPTION = "description"
    ICON = "icon"
    FUNCTION_NAME = "function_name"


class PropKey:
    DISPLAY_NAME = "displayName"
    DESCRIPTION = "description"
    FUNCTION_NAME = "functionName"


class ToolSource:
    INBUILT = "inbuilt"
    CUSTOM = "custom"


class DockerMounts:
    FS_INPUT = "/mnt/unstract/fs_input"
    FS_INPUT_BIND = "/mnt/unstract/fs_input"

    @classmethod
    def mounts(cls) -> dict[str, Any]:
        return {
            cls.FS_INPUT: {"bind": cls.FS_INPUT_BIND, "mode": "rw"},
            # Add more constants if needed
        }


class AdapterPropertyKey:
    ADAPTER_ID_KEY = "adapterIdKey"
    ADAPTER_ID = "adapterId"
    ADAPTER_TYPE = "adapterType"
    # TODO: Define defaults in SDK and use within tools
    DEFAULT_LLM_ADAPTER_ID = "llmAdapterId"
    DEFAULT_EMBEDDING_ADAPTER_ID = "embeddingAdapterId"
    DEFAULT_VECTOR_DB_ADAPTER_ID = "vectorDbAdapterId"
    DEFAULT_X2TEXT_ADAPTER_ID = "x2TextAdapterId"
    DEFAULT_OCR_ADAPTER_ID = "ocrAdapterId"
