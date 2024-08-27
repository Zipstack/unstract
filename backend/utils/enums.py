from enum import Enum


class CeleryTaskState(Enum):
    FAILURE = "FAILURE"
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    RETRY = "RETRY"
    REVOKED = "REVOKED"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
