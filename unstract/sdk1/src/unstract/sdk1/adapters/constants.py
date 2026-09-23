from unstract.sdk1.adapters.enums import AdapterTypes


class AdapterDocs:
    """Documentation links surfaced on the adapter configuration screen."""

    BASE_URL = "https://docs.unstract.com/unstract/unstract_platform/adapters"

    _TYPE_INDEX = {
        AdapterTypes.LLM: f"{BASE_URL}/llms/index/",
        AdapterTypes.EMBEDDING: f"{BASE_URL}/embedding/index/",
        AdapterTypes.VECTOR_DB: f"{BASE_URL}/vector_dbs/index/",
        AdapterTypes.X2TEXT: f"{BASE_URL}/text_extractors/index/",
    }

    @classmethod
    def type_index_url(cls, adapter_type: AdapterTypes) -> str:
        """Category index used by adapters without a dedicated doc page."""
        return cls._TYPE_INDEX.get(adapter_type, f"{cls.BASE_URL}/index/")


class Common:
    METADATA = "metadata"
    MODULE = "module"
    ADAPTER = "adapter"
    SRC_FOLDER = "src"
    ADAPTER_METADATA = "adapter_metadata"
    ICON = "icon"
    ADAPTER_ID = "adapter_id"
    ADAPTER_TYPE = "adapter_type"
    DEFAULT_ERR_MESSAGE = "Something went wrong"
    ADAPTER_ID_GETTER = "get_id"
    ADAPTER_METADATA_GETTER = "get_metadata"
