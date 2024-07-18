class ProfileManagerKeys:
    CREATED_BY = "created_by"
    TOOL_ID = "tool_id"
    PROMPTS = "prompts"
    ADAPTER_NAME = "adapter_name"
    LLM = "llm"
    VECTOR_STORE = "vector_store"
    EMBEDDING_MODEL = "embedding_model"
    X2TEXT = "x2text"
    PROMPT_STUDIO_TOOL = "prompt_studio_tool"
    MAX_PROFILE_COUNT = 4


class ProfileManagerErrors:
    SERIALIZATION_FAILED = "Data Serialization Failed."
    PROFILE_NAME_EXISTS = "A profile with this name already exists."
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    PLATFORM_ERROR = "Seems an error occured in Platform Service."
