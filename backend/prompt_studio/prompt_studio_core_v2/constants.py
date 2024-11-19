from enum import Enum


class ToolStudioKeys:
    CREATED_BY = "created_by"
    TOOL_ID = "tool_id"
    PROMPTS = "prompts"
    PLATFORM_SERVICE_API_KEY = "PLATFORM_SERVICE_API_KEY"
    SUMMARIZE_LLM_PROFILE = "summarize_llm_profile"
    DEFAULT_PROFILE = "default_profile"


class ToolStudioErrors:
    SERIALIZATION_FAILED = "Data Serialization Failed."
    TOOL_NAME_EXISTS = "Tool with the name already exists"
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    PLATFORM_ERROR = "Seems an error occured in Platform Service."
    PROMPT_NAME_EXISTS = "Prompt with the name already exists"


class ToolStudioPromptKeys:
    CREATED_BY = "created_by"
    TOOL_ID = "tool_id"
    RUN_ID = "run_id"
    NUMBER = "Number"
    FLOAT = "Float"
    PG_VECTOR = "Postgres pg_vector"
    ANSWERS = "answers"
    UNIQUE_FILE_ID = "unique_file_id"
    ID = "id"
    FILE_NAME = "file_name"
    FILE_HASH = "file_hash"
    TOOL_ID = "tool_id"
    NAME = "name"
    ACTIVE = "active"
    PROMPT = "prompt"
    CHUNK_SIZE = "chunk-size"
    PROMPTX = "promptx"
    VECTOR_DB = "vector-db"
    EMBEDDING = "embedding"
    X2TEXT_ADAPTER = "x2text_adapter"
    CHUNK_OVERLAP = "chunk-overlap"
    LLM = "llm"
    IS_ASSERT = "is_assert"
    ASSERTION_FAILURE_PROMPT = "assertion_failure_prompt"
    RETRIEVAL_STRATEGY = "retrieval-strategy"
    SIMPLE = "simple"
    TYPE = "type"
    NUMBER = "number"
    EMAIL = "email"
    DATE = "date"
    BOOLEAN = "boolean"
    JSON = "json"
    PREAMBLE = "preamble"
    SIMILARITY_TOP_K = "similarity-top-k"
    PROMPT_TOKENS = "prompt_tokens"
    COMPLETION_TOKENS = "completion_tokens"
    TOTAL_TOKENS = "total_tokens"
    RESPONSE = "response"
    POSTAMBLE = "postamble"
    GRAMMAR = "grammar"
    WORD = "word"
    SYNONYMS = "synonyms"
    OUTPUTS = "outputs"
    SECTION = "section"
    DEFAULT = "default"
    REINDEX = "reindex"
    EMBEDDING_SUFFIX = "embedding_suffix"
    EVAL_METRIC_PREFIX = "eval_"
    EVAL_RESULT_DELIM = "__"
    EVAL_SETTINGS = "eval_settings"
    EVAL_SETTINGS_EVALUATE = "evaluate"
    EVAL_SETTINGS_MONITOR_LLM = "monitor_llm"
    EVAL_SETTINGS_EXCLUDE_FAILED = "exclude_failed"
    SUMMARIZE = "summarize"
    SUMMARIZED_RESULT = "summarized_result"
    DOCUMENT_ID = "document_id"
    EXTRACT = "extract"
    TOOL_SETTINGS = "tool_settings"
    ENABLE_CHALLENGE = "enable_challenge"
    CHALLENGE_LLM = "challenge_llm"
    SINGLE_PASS_EXTRACTION_MODE = "single_pass_extraction_mode"
    SINGLE_PASS_EXTRACTION = "single_pass_extraction"
    NOTES = "NOTES"
    OUTPUT = "output"
    SEQUENCE_NUMBER = "sequence_number"
    PROFILE_MANAGER_ID = "profile_manager"
    CONTEXT = "context"
    METADATA = "metadata"
    INCLUDE_METADATA = "include_metadata"
    TXT_EXTENTION = ".txt"
    TABLE = "table"
    PLATFORM_POSTAMBLE = "platform_postamble"
    SUMMARIZE_AS_SOURCE = "summarize_as_source"
    VARIABLE_MAP = "variable_map"
    RECORD = "record"
    ENABLE_HIGHLIGHT = "enable_highlight"


class FileViewTypes:
    ORIGINAL = "ORIGINAL"
    EXTRACT = "EXTRACT"
    SUMMARIZE = "SUMMARIZE"


class LogLevels:
    INFO = "INFO"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    RUN = "RUN"


class IndexingStatus(Enum):
    PENDING_STATUS = "pending"
    COMPLETED_STATUS = "completed"
    STARTED_STATUS = "started"
    DOCUMENT_BEING_INDEXED = "Document is being indexed"


class DefaultPrompts:
    PREAMBLE = (
        "Your ability to extract and summarize this context accurately "
        "is essential for effective analysis. "
        "Pay close attention to the context's language, structure, and any "
        "cross-references to ensure a comprehensive and precise extraction "
        "of information. Do not use prior knowledge or information from "
        "outside the context to answer the questions. Only use the "
        "information provided in the context to answer the questions."
    )
    POSTAMBLE = (
        "Do not include any explanation in the reply. "
        "Only include the extracted information in the reply."
    )
