from enum import Enum


class PromptServiceContants:
    HELP = "help"
    disallowed_words = [
        "which",
        "what",
        "how",
        "when",
        "where",
        "who",
        "why",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "seem",
        "have",
        "has",
        "had",
        "can",
        "could",
        "may",
        "might",
        "will",
        "would",
        "should",
        "must",
        "shall",
        "did",
        "would",
        "be",
        "many",
        "being",
        "(",
        ")",
        ",",
    ]
    AND = "and"
    TO = "to"
    OR = "or"
    IS = "is"
    DOC_ID = "doc_id"
    WORD = "word"
    SYNONYMS = "synonyms"
    OUTPUTS = "outputs"
    TOOL_ID = "tool_id"
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
    VECTOR_KEYWORD = "vector+keyword"
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


class Query:
    QUERY = "Query"
    DROP_TABLE = "DROP TABLE IF EXISTS nodes;"
    INSERT_INTO = "INSERT INTO nodes VALUES (?, ?, ?)"
    SELECT = "SELECT *,rank FROM nodes WHERE "
    NODE_MATCH = " nodes MATCH ?"
    ORDER_BY = " ORDER BY RANK LIMIT 2;"


class Prompt:
    CONTEXT = "Context"


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
