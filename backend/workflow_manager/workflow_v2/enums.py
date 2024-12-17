from enum import Enum

from utils.common_utils import ModelEnum


class WorkflowExecutionMethod(Enum):
    INSTANT = "INSTANT"
    QUEUED = "QUEUED"


class ExecutionStatus(ModelEnum):
    """An enumeration representing the various statuses of an execution
    process.

    Statuses:
        PENDING: The execution's entry has been created in the database.
        QUEUED: The execution task is queued for asynchronous execution
        INITIATED: The execution has been initiated.
        READY: The execution is ready for the build phase.
        EXECUTING: The execution is currently in progress.
        COMPLETED: The execution has been successfully completed.
        STOPPED: The execution was stopped by the user
            (applicable to step executions).
        ERROR: An error occurred during the execution process.

    Note:
        Intermediate statuses might not be experienced due to
        Django's query triggering once all processes are completed.
    """

    PENDING = "PENDING"
    INITIATED = "INITIATED"
    QUEUED = "QUEUED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class SchemaType(Enum):
    """Possible types for workflow module's JSON schema.

    Values:
        src: Refers to the source module's schema
        dest: Refers to the destination module's schema
    """

    SRC = "src"
    DEST = "dest"


class SchemaEntity(Enum):
    """Possible entities for workflow module's JSON schema.

    Values:
        file: Refers to schema for file based sources
        api: Refers to schema for API based sources
        db: Refers to schema for DB based destinations
    """

    FILE = "file"
    API = "api"
    DB = "db"


class ColumnModes(Enum):
    WRITE_JSON_TO_A_SINGLE_COLUMN = "Write JSON to a single column"
    SPLIT_JSON_INTO_COLUMNS = "Split JSON into columns"


class AgentName(Enum):
    UNSTRACT_DBWRITER = "Unstract/DBWriter"


class RuleLogic(Enum):
    AND = "AND"
    OR = "OR"
