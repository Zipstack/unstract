from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from celery.result import AsyncResult

from workflow_manager.endpoint_v2.dto import DestinationConfig, SourceConfig
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.constants import WorkflowKey


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
    log_id: str | None = None
    status_api: str | None = None
    error: str | None = None
    mode: str | None = None
    result: Any | None = None
    message: str | None = None
    result_acknowledged: bool = False

    def __post_init__(self) -> None:
        self.log_id = self.log_id or None
        self.mode = self.mode or None
        self.error = self.error or None
        self.result = self.result or None
        self.message = self.message or None
        self.status_api = self.status_api or None

    def remove_result_metadata_keys(self, keys_to_remove: list[str] = []) -> None:
        """Removes specified keys from the 'metadata' dictionary within each
        'result' dictionary in the 'result' list attribute of the instance. If
        'keys_to_remove' is empty, the 'metadata' key itself is removed.

        Args:
            keys_to_remove (List[str]): List of keys to be removed from 'metadata'.
        """
        if not isinstance(self.result, list):
            return

        for item in self.result:
            if not isinstance(item, dict):
                break

            result = item.get("result")
            if not isinstance(result, dict):
                break

            self._remove_specific_keys(result=result, keys_to_remove=keys_to_remove)

    def remove_result_metrics(self) -> None:
        """Removes the 'metrics' key from the 'result' dictionary within each
        'result' dictionary in the 'result' list attribute of the instance.
        """
        if not isinstance(self.result, list):
            return

        for item in self.result:
            if not isinstance(item, dict):
                continue

            result = item.get("result")
            if isinstance(result, dict):
                result.pop("metrics", None)

    def _remove_specific_keys(self, result: dict, keys_to_remove: list[str]) -> None:
        """Removes specified keys from the 'metadata' dictionary within the
        provided 'result' dictionary. If 'keys_to_remove' is empty, the
        'metadata' dictionary is cleared.

        Args:
            result (dict): The dictionary containing the 'metadata' key.
            keys_to_remove (List[str]): List of keys to be removed from 'metadata'.
        """
        metadata = result.get("metadata", {})
        if keys_to_remove:
            for key in keys_to_remove:
                metadata.pop(key, None)
        else:
            metadata = {}
        self._update_metadata(result=result, metadata=metadata)

    def _update_metadata(self, result: dict, metadata: dict) -> None:
        """Updates the 'metadata' key in the provided 'result' dictionary. If
        'metadata' is empty, removes the 'metadata' key from 'result'.

        Args:
            result (dict): The dictionary to be updated.
            metadata (dict): The new metadata dictionary to be set. If empty, 'metadata'
                is removed.
        """
        if metadata:
            result["metadata"] = metadata
        else:
            result.pop("metadata", None)


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


@dataclass
class FileData:
    workflow_id: str
    source_config: dict[str, Any]
    destination_config: dict[str, Any]
    execution_id: str
    single_step: bool
    organization_id: str
    pipeline_id: str
    scheduled: bool
    execution_mode: str
    use_file_history: bool
    q_file_no_list: list[int]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileData:
        field_names = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data)

    def __str__(self) -> str:
        return f"FileData({self.__dict__})"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileBatchData:
    files: list
    file_data: FileData

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileBatchData:
        file_data = FileData.from_dict(data["file_data"])
        return cls(files=data["files"], file_data=file_data)

    def __str__(self) -> str:
        return f"FileBatchData(files={self.files}, file_data={self.file_data})"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileBatchResult:
    successful_files: int = 0
    failed_files: int = 0

    @property
    def total_files(self) -> int:
        return self.successful_files + self.failed_files

    def to_dict(self) -> dict[str, int]:
        return {
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
        }


@dataclass
class ToolExecutionResult:
    error: str | None
    result: Any | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "result": self.result,
        }


@dataclass
class FinalOutputResult:
    output: Any | None
    metadata: dict[str, Any] | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class ExecutionContext:
    workflow_log: WorkflowLog
    workflow_file_execution: WorkflowFileExecution
    source_config: SourceConfig
    destination_config: DestinationConfig
