from enum import Enum


class ExecutionEntity(Enum):
    ETL = "ETL"
    API = "API"
    TASK = "TASK"
    WORKFLOW = "WF"
