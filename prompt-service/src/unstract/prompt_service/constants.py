from enum import Enum


class PromptServiceContants:
    WORD = "word"
    SYNONYMS = "synonyms"
    OUTPUTS = "outputs"
    TOOL_ID = "tool_id"
    RUN_ID = "run_id"
    FILE_NAME = "file_name"
    FILE_HASH = "file_hash"
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
    SUBQUESTION = "subquestion"
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
    PLATFORM_SERVICE_API_KEY = "PLATFORM_SERVICE_API_KEY"
    EMBEDDING_SUFFIX = "embedding_suffix"
    EVAL_SETTINGS = "eval_settings"
    EVAL_SETTINGS_EVALUATE = "evaluate"
    EVAL_SETTINGS_MONITOR_LLM = "monitor_llm"
    EVAL_SETTINGS_EXCLUDE_FAILED = "exclude_failed"
    TOOL_SETTINGS = "tool_settings"
    LOG_EVENTS_ID = "log_events_id"
    CHALLENGE_LLM = "challenge_llm"
    CHALLENGE = "challenge"
    ENABLE_CHALLENGE = "enable_challenge"
    EXTRACTION = "extraction"
    SUMMARIZE = "summarize"
    SINGLE_PASS_EXTRACTION = "single-pass-extraction"
    SIMPLE_PROMPT_STUDIO = "simple-prompt-studio"
    LLM_USAGE_REASON = "llm_usage_reason"
    METADATA = "metadata"
    OUTPUT = "output"
    CONTEXT = "context"
    INCLUDE_METADATA = "include_metadata"
    TABLE = "table"
    TABLE_SETTINGS = "table_settings"
    EPILOGUE = "epilogue"
    PLATFORM_POSTAMBLE = "platform_postamble"
    HIGHLIGHT_DATA_PLUGIN = "highlight-data"
    CLEAN_CONTEXT = "clean-context"
    SUMMARIZE_AS_SOURCE = "summarize_as_source"
    VARIABLE_MAP = "variable_map"
    RECORD = "record"
    TEXT = "text"
    ENABLE_HIGHLIGHT = "enable_highlight"
    FILE_PATH = "file_path"
    HIGHLIGHT_DATA = "highlight_data"
    CONFIDENCE_DATA = "confidence_data"
    REQUIRED_FIELDS = "required_fields"
    REQUIRED = "required"
    EXECUTION_SOURCE = "execution_source"
    METRICS = "metrics"
    LINE_ITEM = "line-item"
    LINE_NUMBERS = "line_numbers"


class RunLevel(Enum):
    """Different stages of prompt execution.

    Comprises of prompt run and response evaluation stages.
    """

    RUN = "RUN"
    EVAL = "EVAL"
    CHALLENGE = "CHALLENGE"
    TABLE_EXTRACTION = "TABLE_EXTRACTION"


class DBTableV2:
    """Database tables."""

    ORGANIZATION = "organization"
    ADAPTER_INSTANCE = "adapter_instance"
    PROMPT_STUDIO_REGISTRY = "prompt_studio_registry"
    PLATFORM_KEY = "platform_key"
    TOKEN_USAGE = "usage"


class FileStorageKeys:
    PERMANENT_REMOTE_STORAGE = "PERMANENT_REMOTE_STORAGE"
    TEMPORARY_REMOTE_STORAGE = "TEMPORARY_REMOTE_STORAGE"


class FileStorageType(Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"


class ExecutionSource(Enum):
    IDE = "ide"
    TOOL = "tool"
