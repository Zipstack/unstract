"""Constants for the Look-Up system."""


class LookupProfileManagerKeys:
    """Keys used in LookupProfileManager serialization."""

    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    LOOKUP_PROJECT = "lookup_project"
    PROFILE_NAME = "profile_name"
    LLM = "llm"
    VECTOR_STORE = "vector_store"
    EMBEDDING_MODEL = "embedding_model"
    X2TEXT = "x2text"
    CHUNK_SIZE = "chunk_size"
    CHUNK_OVERLAP = "chunk_overlap"
    SIMILARITY_TOP_K = "similarity_top_k"
    IS_DEFAULT = "is_default"
    REINDEX = "reindex"


class LookupProfileManagerErrors:
    """Error messages for LookupProfileManager operations."""

    SERIALIZATION_FAILED = "Data serialization failed."
    PROFILE_NAME_EXISTS = "A profile with this name already exists for this project."
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    NO_DEFAULT_PROFILE = "No default profile found for this project."
