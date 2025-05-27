from dataclasses import asdict, dataclass, field
from typing import Any

from unstract.sdk.adapters.enums import AdapterTypes
from unstract.tool_registry.constants import AdapterPropertyKey


@dataclass
class ToolMeta:
    tool: str
    tool_type: str
    tool_path: str
    image_name_with_tag: str
    image_name: str
    tag: str


@dataclass
class ResourceRequire:
    input: bool = False
    output: bool = False


@dataclass
class PropertyRequire:
    files: ResourceRequire = field(default_factory=ResourceRequire)
    databases: ResourceRequire = field(default_factory=ResourceRequire)


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str


@dataclass
class Spec:
    """A data class representing the tool specs.

    Attributes:
        title (str): The title of the tool.
        description (str): The description of the tool.
        type (str): The type of the schema.
        required (list[str]): A list of required properties for the tool.
        properties (dict[str, Any]): A dictionary of properties for the tool.

    Methods:
        to_json(self) -> dict[str, Any]:
            Converts the Spec object to a JSON format.

    Returns:
                dict[str, Any]: The Spec object in JSON format.
    """

    TITLE_KEY = "title"
    TYPE_KEY = "type"
    DESCRIPTION_KEY = "description"
    REQUIRED_KEY = "required"
    PROPERTIES_KEY = "properties"

    title: str = ""
    description: str = ""
    type: str = "object"
    required: list[str] = field(default_factory=list)
    properties: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]]
    )

    def get_adapter_properties_keys(self, adapter_type: AdapterTypes) -> set[str]:
        properties = set()
        if self.properties is not None:
            properties = {
                key
                for key, item in self.properties.items()
                if item.get("adapterType") == adapter_type.value
            }
        return properties

    def get_llm_adapter_properties_keys(self) -> set[str]:
        return self.get_adapter_properties_keys(AdapterTypes.LLM)

    def get_embedding_adapter_properties_keys(self) -> set[str]:
        return self.get_adapter_properties_keys(AdapterTypes.EMBEDDING)

    def get_vector_db_adapter_properties_keys(self) -> set[str]:
        return self.get_adapter_properties_keys(AdapterTypes.VECTOR_DB)

    def get_text_extractor_adapter_properties_keys(self) -> set[str]:
        return self.get_adapter_properties_keys(AdapterTypes.X2TEXT)

    def get_ocr_adapter_properties_keys(self) -> set[str]:
        return self.get_adapter_properties_keys(AdapterTypes.OCR)

    def get_adapter_properties(
        self, adapter_type: AdapterTypes
    ) -> dict[str, dict[str, Any]]:
        properties = {}

        if self.properties is not None:
            properties = {
                key: item
                for key, item in self.properties.items()
                if item.get("adapterType") == adapter_type.value
            }
        return properties

    def get_llm_adapter_properties(self) -> dict[str, dict[str, Any]]:
        return self.get_adapter_properties(AdapterTypes.LLM)

    def get_embedding_adapter_properties(self) -> dict[str, dict[str, Any]]:
        return self.get_adapter_properties(AdapterTypes.EMBEDDING)

    def get_vector_db_adapter_properties(self) -> dict[str, dict[str, Any]]:
        return self.get_adapter_properties(AdapterTypes.VECTOR_DB)

    def get_text_extractor_adapter_properties(
        self,
    ) -> dict[str, dict[str, Any]]:
        return self.get_adapter_properties(AdapterTypes.X2TEXT)

    def get_ocr_adapter_properties(
        self,
    ) -> dict[str, dict[str, Any]]:
        return self.get_adapter_properties(AdapterTypes.OCR)

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> "Spec":
        title = data_dict.get(cls.TITLE_KEY, "")
        description = data_dict.get(cls.DESCRIPTION_KEY, "")
        spec_type = data_dict.get(cls.TYPE_KEY, "")
        required = data_dict.get(cls.REQUIRED_KEY, [])
        properties = data_dict.get(cls.PROPERTIES_KEY, {})

        return cls(
            title=title,
            description=description,
            type=spec_type,
            required=required,
            properties=properties,
        )

    def to_dict(self) -> dict[str, Any]:
        """Spec to json format.

        Returns:
            _type_: _description_
        """
        _dict = asdict(self)
        return _dict


@dataclass
class AdapterProperties:
    """A data class representing properties of an adapter as part of tool
    properties.

    Attributes:
        IS_ENABLED_KEY (str): Constant for the key "isEnabled".
        IS_REQUIRED_KEY (str): Constant for the key "isRequired".
        TITLE_KEY (str): Constant for the key "title".
        DESCRIPTION_KEY (str): Constant for the key "description".

        is_enabled (bool): Whether the adapter is enabled in the tool.
            Defaults to False.
        is_required (bool): Whether the adapter is required in the tool spec.
            Defaults to False.
        title (Optional[str]): The title of the adapter. Defaults to None.
        description (Optional[str]): The description of the adapter.
            Defaults to None.

    Methods:
        from_dict(cls, data_dict: dict[str, Any]) -> "AdapterProperties":
            Creates an instance of AdapterProperties from a dictionary.
    """

    # Constants for keys
    IS_ENABLED_KEY = "isEnabled"
    IS_REQUIRED_KEY = "isRequired"
    TITLE_KEY = "title"
    DESCRIPTION_KEY = "description"
    ADAPTER_ID_KEY = AdapterPropertyKey.ADAPTER_ID

    is_enabled: bool = False
    is_required: bool = False
    title: str | None = None
    description: str | None = None
    adapter_id: str | None = None

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> "AdapterProperties":
        return cls(
            is_enabled=data_dict.get(cls.IS_ENABLED_KEY, False),
            is_required=data_dict.get(cls.IS_REQUIRED_KEY, False),
            title=data_dict.get(cls.TITLE_KEY),
            description=data_dict.get(cls.DESCRIPTION_KEY),
            adapter_id=data_dict.get(cls.ADAPTER_ID_KEY),
        )

    def to_dict(self) -> dict[str, Any]:
        """Get AdapterProperties as a dictionary.

        Returns:
            dict[str, Any]: AdapterProperties as a dictionary
        """
        return {
            self.IS_ENABLED_KEY: self.is_enabled,
            self.IS_REQUIRED_KEY: self.is_required,
            self.TITLE_KEY: self.title,
            self.DESCRIPTION_KEY: self.description,
        }


@dataclass
class Adapter:
    """A data class representing an adapter.

    Attributes:
        LANGUAGE_MODELS_KEY (str): Constant for the key "languageModels".
        EMBEDDING_SERVICES_KEY (str): Constant for the key "embeddingServices".
        VECTOR_STORES_KEY (str): Constant for the key "vectorStores".
        TEXT_EXTRACTORS_KEY (str): Constant for the key "textExtractors".
        OCR_KEY (str): Constant for the key "ocr".

        language_model (AdapterProperties): The properties of the language model
        adapter.
        embedding_service (AdapterProperties): The properties of the embedding
        service adapter.
        vector_store (AdapterProperties): The properties of the vector store
        adapter.

    Methods:
        from_dict(cls, data_dict: dict[str, Any]) -> Adapter:
            Creates an instance of Adapter from a dictionary.
    """

    # Constants for keys
    LANGUAGE_MODELS_KEY = "languageModels"
    EMBEDDING_SERVICES_KEY = "embeddingServices"
    VECTOR_STORES_KEY = "vectorStores"
    TEXT_EXTRACTORS_KEY = "textExtractors"
    OCRS_KEY = "ocrs"

    language_models: list[AdapterProperties] = field(
        default_factory=list[AdapterProperties]
    )
    embedding_services: list[AdapterProperties] = field(
        default_factory=list[AdapterProperties]
    )
    vector_stores: list[AdapterProperties] = field(
        default_factory=list[AdapterProperties]
    )
    text_extractors: list[AdapterProperties] = field(
        default_factory=list[AdapterProperties]
    )
    ocrs: list[AdapterProperties] = field(default_factory=list[AdapterProperties])

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> "Adapter":
        language_models_list = data_dict.get(cls.LANGUAGE_MODELS_KEY, [])
        embedding_services_list = data_dict.get(cls.EMBEDDING_SERVICES_KEY, [])
        vector_stores_list = data_dict.get(cls.VECTOR_STORES_KEY, [])
        text_extractors_list = data_dict.get(cls.TEXT_EXTRACTORS_KEY, [])
        ocrs_list = data_dict.get(cls.OCRS_KEY, [])

        language_models = [
            AdapterProperties.from_dict(language_model_dict)
            for language_model_dict in language_models_list
        ]
        embedding_services = [
            AdapterProperties.from_dict(embedding_service_dict)
            for embedding_service_dict in embedding_services_list
        ]
        vector_stores = [
            AdapterProperties.from_dict(vector_store_dict)
            for vector_store_dict in vector_stores_list
        ]
        text_extractors = [
            AdapterProperties.from_dict(text_extractor_dict)
            for text_extractor_dict in text_extractors_list
        ]
        ocrs = [AdapterProperties.from_dict(ocr_dict) for ocr_dict in ocrs_list]

        return cls(
            language_models=language_models,
            embedding_services=embedding_services,
            vector_stores=vector_stores,
            text_extractors=text_extractors,
            ocrs=ocrs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Spec to json format.

        Returns:
            _type_: _description_
        """
        _dict = asdict(self)
        return _dict


@dataclass
class Properties:
    # Constants for keys
    DISPLAY_NAME_KEY = "displayName"
    FUNCTION_NAME_KEY = "functionName"
    DESCRIPTION_KEY = "description"
    ADAPTER_KEY = "adapter"
    TOOL_VERSION_KEY = "toolVersion"

    display_name: str = ""
    function_name: str = ""
    description: str = ""
    tool_version: str = ""
    adapter: Adapter = field(default_factory=Adapter)

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> "Properties":
        display_name = data_dict.get(cls.DISPLAY_NAME_KEY, "")
        function_name = data_dict.get(cls.FUNCTION_NAME_KEY, "")
        description = data_dict.get(cls.DESCRIPTION_KEY, "")
        tool_version = data_dict.get(cls.TOOL_VERSION_KEY, "")
        adapter_dict = data_dict.get(cls.ADAPTER_KEY, {})
        adapter = Adapter.from_dict(adapter_dict)
        return cls(
            display_name=display_name,
            function_name=function_name,
            description=description,
            tool_version=tool_version,
            adapter=adapter,
        )

    def to_dict(self) -> dict[str, Any]:
        """Get Properties as a dictionary.

        Returns:
            dict[str, Any]: Properties for the tool
        """
        camel_case_dict = {
            "displayName": self.display_name,
            "functionName": self.function_name,
            "description": self.description,
            "toolVersion": self.tool_version,
            "adapter": self.adapter.to_dict(),
        }
        return camel_case_dict


@dataclass
class Tool:
    # Constants for keys
    TOOL_UID_KEY = "tool_uid"
    PROPERTIES_KEY = "properties"
    VARIABLES_KEY = "variables"
    SPEC_KEY = "spec"
    ICON_KEY = "icon"
    IMAGE_URL_KEY = "image_url"
    IMAGE_NAME_KEY = "image_name"
    IMAGE_TAG_KEY = "image_tag"

    tool_uid: str = ""
    properties: Properties = field(default_factory=Properties)
    spec: Spec = field(default_factory=Spec)
    variables: dict[str, Any] = field(default_factory=dict)
    icon: str = ""
    image_url: str = ""
    image_name: str = ""
    image_tag: str = ""

    @classmethod
    def from_dict(cls, tool_uid: str, data_dict: dict[str, Any]) -> "Tool":
        properties_dict = data_dict.get(cls.PROPERTIES_KEY, {})
        properties = Properties.from_dict(properties_dict)
        spec_dict = data_dict.get(cls.SPEC_KEY, {})
        spec = Spec.from_dict(spec_dict)

        return cls(
            tool_uid=tool_uid,
            properties=properties,
            spec=spec,
            variables=data_dict.get(cls.VARIABLES_KEY, {}),
            icon=data_dict.get(cls.ICON_KEY, ""),
            image_url=data_dict.get(cls.IMAGE_URL_KEY, ""),
            image_name=data_dict.get(cls.IMAGE_NAME_KEY, ""),
            image_tag=data_dict.get(cls.IMAGE_TAG_KEY, ""),
        )

    def to_json(cls) -> dict[str, Any]:
        """Tool to json format.

        Returns:
            _type_: _description_
        """
        tool_dict = asdict(cls)
        return tool_dict

    def get_image(cls) -> str:
        if cls.image_tag:
            image_name_with_tag = f"{cls.image_name}:{cls.image_tag}"
            return image_name_with_tag
        else:
            # Handle the case when tag is None
            return cls.image_name


@dataclass
class ToolData:
    uid: str
    data: dict[str, Any]
