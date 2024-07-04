import logging
from typing import Any

from utils.constants import Common

from unstract.connectors.queues import connectors as queue_connectors
from unstract.connectors.queues.unstract_queue import UnstractQueue

logger = logging.getLogger(__name__)


from dataclasses import dataclass
from enum import Enum
from typing import Any


class QueueResultStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    # Add other statuses as needed


class ConnectorError(Exception):
    """Custom exception for connection-related errors."""

    pass


class QueueUtils:
    @staticmethod
    def get_queue_inst(connector_settings: dict[str, Any] = {}) -> UnstractQueue:
        if not queue_connectors:
            raise ConnectorError("Queue connector not exists")
        queue_connector_key = next(iter(queue_connectors))
        connector = queue_connectors[queue_connector_key][Common.METADATA][
            Common.CONNECTOR
        ]
        connector_class: UnstractQueue = connector(connector_settings)
        return connector_class


@dataclass
class QueueResult:
    file: str
    whisper_hash: str
    status: QueueResultStatus
    result: Any
    workflow_id: str
    file_content: str
