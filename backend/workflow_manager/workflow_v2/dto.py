from dataclasses import dataclass
from typing import Any, Optional

from celery.result import AsyncResult
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
