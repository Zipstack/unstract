from enum import Enum


class ToolStudioKeys:
    CREATED_BY = "created_by"
    TOOL_ID = "tool_id"
    PROMPTS = "prompts"
    PLATFORM_SERVICE_API_KEY = "PLATFORM_SERVICE_API_KEY"
    SUMMARIZE_LLM_PROFILE = "summarize_llm_profile"
    SUMMARIZE_LLM_ADAPTER = "summarize_llm_adapter"
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
    EXECUTION_ID = "execution_id"
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
    FILE_PATH = "file_path"
    ENABLE_HIGHLIGHT = "enable_highlight"
    REQUIRED = "required"
    EXECUTION_SOURCE = "execution_source"
    LINE_ITEM = "line-item"
    # Webhook postprocessing settings
    ENABLE_POSTPROCESSING_WEBHOOK = "enable_postprocessing_webhook"
    POSTPROCESSING_WEBHOOK_URL = "postprocessing_webhook_url"

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


class ExecutionSource(Enum):
    """Enum to indicate the source of invocation.
    Any new sources can be added to this enum.
    This is to indicate the prompt service.

    Args:
        Enum (_type_): ide/tool
    """

    IDE = "ide"


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
    RUN_ID = "run_id"


class DefaultValues:
    """Default values used throughout the prompt studio helper."""

    DEFAULT_PROFILE_NAME = "Default Profile"
    DEFAULT_SAMPLE_PROFILE_NAME = "sample profile"
    DEFAULT_CHUNK_SIZE = 0
    DEFAULT_CHUNK_OVERLAP = 0
    DEFAULT_SECTION = "Default"
    DEFAULT_RETRIEVAL_STRATEGY = "simple"
    DEFAULT_SIMILARITY_TOP_K = 3
    DEFAULT_EXCLUDE_FAILED = True
    DEFAULT_ENABLE_CHALLENGE = False
    DEFAULT_ENABLE_HIGHLIGHT = False
    DEFAULT_SUMMARIZE_AS_SOURCE = False
    DEFAULT_SUMMARIZE_CONTEXT = False
    DEFAULT_SINGLE_PASS_EXTRACTION_MODE = False
    DEFAULT_EVALUATE = True
    DEFAULT_EVAL_QUALITY_FAITHFULNESS = True
    DEFAULT_EVAL_QUALITY_CORRECTNESS = True
    DEFAULT_EVAL_QUALITY_RELEVANCE = True
    DEFAULT_EVAL_SECURITY_PII = True
    DEFAULT_EVAL_GUIDANCE_TOXICITY = True
    DEFAULT_EVAL_GUIDANCE_COMPLETENESS = True
    DEFAULT_IS_ASSERT = False
    DEFAULT_ACTIVE = True
    DEFAULT_REQUIRED = True
    DEFAULT_ENFORCE_TYPE = "text"
    DEFAULT_ICON = ""
    DEFAULT_PREAMBLE = ""
    DEFAULT_POSTAMBLE = ""
    DEFAULT_SUMMARIZE_PROMPT = ""
    DEFAULT_METADATA = {}
