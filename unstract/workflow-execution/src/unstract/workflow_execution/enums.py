from enum import Enum


class ExecutionType(Enum):
    COMPLETE = "COMPLETE"
    STEP = "STEP"


class ExecutionAction(Enum):
    START = "START"
    NEXT = "NEXT"
    STOP = "STOP"
    CONTINUE = "CONTINUE"


class LogStage(Enum):
    """A enum class representing the different states of a log.

    Attributes:
        COMPILE (str): The state when the workflow is being compiled.
        BUILD (str): The state when the workflow is being built.
        RUN (str): The state when the workflow is being run.
        BEGIN_WORKFLOW (str): The state when the workflow is beginning.
        END_WORKFLOW (str): The state when the workflow is ending.
        PROGRESS_MAX_UPDATE (str): The state when the progress maximum is
        being updated.
        SUCCESS (str): The state when the execution is successful.
        ERROR (str): The state when an error occurs in the workflow.
        MESSAGE (str): The state when a message is being logged.
    """

    COMPILE = "COMPILE"
    BUILD = "BUILD"
    TOOL = "TOOL"
    RUN = "RUN"
    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"
    INITIALIZE = "INITIALIZE"
    PROCESSING = "PROCESSING"


class LogState(Enum):
    """A enum class representing the different states of a log.

    Attributes:
        COMPILE (str): The state when the workflow is being compiled.
        BUILD (str): The state when the workflow is being built.
        RUN (str): The state when the workflow is being run.
        BEGIN_WORKFLOW (str): The state when the workflow is beginning.
        END_WORKFLOW (str): The state when the workflow is ending.
        PROGRESS_MAX_UPDATE (str): The state when the progress maximum is
        being updated.
        SUCCESS (str): The state when the execution is successful.
        ERROR (str): The state when an error occurs in the workflow.
        MESSAGE (str): The state when a message is being logged.
    """

    RUNNING = "RUNNING"
    BEGIN_WORKFLOW = "BEGIN_WORKFLOW"
    END_WORKFLOW = "END_WORKFLOW"
    PROGRESS_MAX_UPDATE = "PROGRESS_MAX_UPDATE"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    MESSAGE = "MESSAGE"
    OUTPUT_UPDATE = "OUTPUT_UPDATE"
    INPUT_UPDATE = "INPUT_UPDATE"
    NEXT = "NEXT"


class LogComponent(Enum):
    """A enum class representing different log components used for UI
    representation.

    Attributes:
        STATUS_BAR (str): The log component for the status bar.
        SOURCE (str): The log component for the source block.
        DESTINATION (str): The log component for the destination block.
    """

    STATUS_BAR = "STATUS_BAR"
    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"
    WORKFLOW = "WORKFLOW"
    NEXT_STEP = "NEXT_STEP"


class LogType(Enum):
    """A enum class representing different types of log entries.

    Attributes:
        LOG (str): Represents a log entry.
        UPDATE (str): Represents a log update component entry.
    """

    LOG = "LOG"
    UPDATE = "UPDATE"


class LogLevel(Enum):
    INFO = "INFO"
    ERROR = "ERROR"
