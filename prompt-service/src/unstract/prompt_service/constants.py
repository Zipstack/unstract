from enum import Enum


class PromptServiceConstants:
    """Constants used in the prompt service."""

    WORD = "word"
    SYNONYMS = "synonyms"
    OUTPUTS = "outputs"
    TOOL_ID = "tool_id"
    RUN_ID = "run_id"
    EXECUTION_ID = "execution_id"
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
    WHISPER_HASH = "whisper_hash"
    PAID_FEATURE_MSG = (
        "It is a cloud / enterprise feature. If you have purchased a plan and still "
        "face this issue, please contact support"
    )
    NO_CONTEXT_ERROR = (
        "Couldn't fetch context from vector DB. "
        "This happens usually due to a delay by the Vector DB "
        "provider to confirm writes to DB. "
        "Please try again after some time"
    )
    COMBINED_PROMPT = "combined_prompt"
    TOOL = "tool"
    JSON_POSTAMBLE = "JSON_POSTAMBLE"
    DEFAULT_JSON_POSTAMBLE = "Wrap the final JSON result inbetween ### like below example:\n###\n<FINAL_JSON_RESULT>\n###"
    DOCUMENT_TYPE = "document_type"


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
    """File storage keys."""

    PERMANENT_REMOTE_STORAGE = "PERMANENT_REMOTE_STORAGE"
    TEMPORARY_REMOTE_STORAGE = "TEMPORARY_REMOTE_STORAGE"


class FileStorageType(Enum):
    """File storage type."""

    PERMANENT = "permanent"
    TEMPORARY = "temporary"


class ExecutionSource(Enum):
    """Execution source."""

    IDE = "ide"
    TOOL = "tool"


class VariableType(str, Enum):
    """Type of variable."""

    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class VariableConstants:
    """Constants for variable extraction."""

    VARIABLE_REGEX = "{{(.+?)}}"
    DYNAMIC_VARIABLE_DATA_REGEX = r"\[(.*?)\]"
    DYNAMIC_VARIABLE_URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"  # noqa: E501


class IndexingConstants:
    TOOL_ID = "tool_id"
    EMBEDDING_INSTANCE_ID = "embedding_instance_id"
    VECTOR_DB_INSTANCE_ID = "vector_db_instance_id"
    X2TEXT_INSTANCE_ID = "x2text_instance_id"
    FILE_PATH = "file_path"
    CHUNK_SIZE = "chunk_size"
    CHUNK_OVERLAP = "chunk_overlap"
    REINDEX = "reindex"
    FILE_HASH = "file_hash"
    OUTPUT_FILE_PATH = "output_file_path"
    ENABLE_HIGHLIGHT = "enable_highlight"
    USAGE_KWARGS = "usage_kwargs"
    PROCESS_TEXT = "process_text"
    EXTRACTED_TEXT = "extracted_text"
    TAGS = "tags"
    EXECUTION_SOURCE = "execution_source"
    DOC_ID = "doc_id"
    TOOL_EXECUTION_METATADA = "tool_execution_metadata"
    EXECUTION_DATA_DIR = "execution_data_dir"
    METADATA_FILE = "METADATA.json"
