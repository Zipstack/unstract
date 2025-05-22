from dataclasses import dataclass
from typing import Any

from workflow_manager.workflow_v2.enums import ExecutionStatus


class ExecutionCacheFields:
    WORKFLOW_ID = "workflow_id"
    EXECUTION_ID = "execution_id"
    STATUS = "status"
    TOTAL_FILES = "total_files"
    COMPLETED_FILES = "completed_files"
    FAILED_FILES = "failed_files"


@dataclass
class ExecutionCache:
    workflow_id: str
    execution_id: str
    status: ExecutionStatus
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0

    def __post_init__(self):
        self.workflow_id = str(self.workflow_id)
        self.execution_id = str(self.execution_id)
        self.status = ExecutionStatus(self.status)

    def to_json(self) -> dict[str, Any]:
        return {
            ExecutionCacheFields.WORKFLOW_ID: self.workflow_id,
            ExecutionCacheFields.EXECUTION_ID: self.execution_id,
            ExecutionCacheFields.STATUS: self.status.value,
            ExecutionCacheFields.TOTAL_FILES: self.total_files,
            ExecutionCacheFields.COMPLETED_FILES: self.completed_files,
            ExecutionCacheFields.FAILED_FILES: self.failed_files,
        }
