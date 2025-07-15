import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.constants import Common
from workflow_manager.endpoint_v2.exceptions import UnstractQueueException

from unstract.connectors.queues import connectors as queue_connectors
from unstract.connectors.queues.unstract_queue import UnstractQueue

logger = logging.getLogger(__name__)


class QueueResultStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    # Add other statuses as needed


class QueueUtils:
    @staticmethod
    def get_queue_inst(connector_settings: dict[str, Any] = {}) -> UnstractQueue:
        if not queue_connectors:
            raise UnstractQueueException(detail="Queue connector not exists")
        queue_connector_key = next(iter(queue_connectors))
        connector = queue_connectors[queue_connector_key][Common.METADATA][
            Common.CONNECTOR
        ]
        connector_class: UnstractQueue = connector(connector_settings)
        return connector_class


@dataclass
class QueueResult:
    file: str
    status: QueueResultStatus
    result: Any
    workflow_id: str
    file_content: str
    whisper_hash: str | None = None
    file_execution_id: str | None = None

    def to_dict(self) -> Any:
        return {
            "file": self.file,
            "whisper_hash": self.whisper_hash,
            "status": self.status.value,  # Convert enum to string value
            "result": self.result,
            "workflow_id": self.workflow_id,
            "file_content": self.file_content,
            "file_execution_id": self.file_execution_id,
        }
