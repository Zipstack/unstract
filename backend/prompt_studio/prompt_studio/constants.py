class ToolStudioPromptKeys:
    CREATED_BY = "created_by"
    TOOL_ID = "tool_id"
    NUMBER = "Number"
    FLOAT = "Float"
    PG_VECTOR = "Postgres pg_vector"
    ANSWERS = "answers"
    UNIQUE_FILE_ID = "unique_file_id"
    ID = "id"
    FILE_NAME = "file_name"
    UNDEFINED = "undefined"
    ACTIVE = "active"
    PROMPT_KEY = "prompt_key"
    EVAL_METRIC_PREFIX = "eval_"
    EVAL_RESULT_DELIM = "__"
    SEQUENCE_NUMBER = "sequence_number"
    START_SEQUENCE_NUMBER = "start_sequence_number"
    END_SEQUENCE_NUMBER = "end_sequence_number"
    PROMPT_ID = "prompt_id"


class ToolStudioPromptErrors:
    SERIALIZATION_FAILED = "Data Serialization Failed."
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    PROMPT_NAME_EXISTS = "Prompt with the name already exists"


class LogLevels:
    INFO = "INFO"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    RUN = "RUN"
