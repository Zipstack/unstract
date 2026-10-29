from enum import Enum, StrEnum


class ExecutionEntity(Enum):
    ETL = "ETL"
    API = "API"
    TASK = "TASK"
    WORKFLOW = "WF"


class AbortOutcome(StrEnum):
    """Per-id answer of the abort endpoint."""

    ABORTED = "aborted"
    ALREADY_FINISHED = "already_finished"
    NOT_PERMITTED = "not_permitted"
