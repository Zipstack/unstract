from enum import Enum


class ContainerStatus(Enum):
    RUNNING = "RUNNING"
    EXITED = "EXITED"
    CREATED = "CREATED"
    PAUSED = "PAUSED"
    RESTARTING = "RESTARTING"
    REMOVING = "REMOVING"
    DEAD = "DEAD"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
