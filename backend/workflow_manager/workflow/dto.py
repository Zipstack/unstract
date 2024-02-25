from dataclasses import dataclass
from typing import Any, Optional

from celery.result import AsyncResult
from workflow_manager.workflow.constants import WorkflowKey


@dataclass
class ProvisionalWorkflow:
    result: str
    output: dict[str, str]
    cost_type: str
    cost: str
    time_taken: float

    def __init__(self, input_dict: dict[str, Any]) -> None:
        self.result = input_dict.get(WorkflowKey.PWF_RESULT, "")
        self.output = input_dict.get(WorkflowKey.PWF_OUTPUT, {})
        self.cost_type = input_dict.get(WorkflowKey.PWF_COST_TYPE, "")
        self.cost = input_dict.get(WorkflowKey.PWF_COST, "")
        self.time_taken = input_dict.get(WorkflowKey.PWF_TIME_TAKEN, 0.0)


@dataclass
class ExecutionResponse:
    workflow_id: str
    execution_id: str
    execution_status: str
    log_id: Optional[str] = None
    status_api: Optional[str] = None
    error: Optional[str] = None
    mode: Optional[str] = None
    result: Optional[Any] = None
    message: Optional[str] = None

    def __post_init__(self) -> None:
        self.log_id = self.log_id or None
        self.mode = self.mode or None
        self.error = self.error or None
        self.result = self.result or None
        self.message = self.message or None
        self.status_api = self.status_api or None


@dataclass
class AsyncResultData:
    id: str
    status: str
    result: Any
    is_ready: bool
    is_failed: bool
    info: Any

    def __init__(self, async_result: AsyncResult):
        self.id = async_result.id
        self.status = async_result.status
        self.result = async_result.result
        self.is_ready = async_result.ready()
        self.is_failed = async_result.failed()
        self.info = async_result.info
        if isinstance(self.result, Exception):
            self.result = str(self.result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result": self.result,
        }
