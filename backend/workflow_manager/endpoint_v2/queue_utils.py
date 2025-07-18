import logging
import time
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

    @staticmethod
    def calculate_remaining_ttl(
        enqueued_at: float, original_ttl_seconds: int
    ) -> int | None:
        """Calculate remaining TTL based on original enqueue time and TTL.

        Args:
            enqueued_at: Timestamp when record was first enqueued
            original_ttl_seconds: Original TTL in seconds

        Returns:
            Remaining TTL in seconds, or None if expired
        """
        if original_ttl_seconds is None:
            return None  # Unlimited TTL

        current_time = time.time()
        elapsed_time = current_time - enqueued_at
        remaining_ttl = original_ttl_seconds - int(elapsed_time)

        return max(0, remaining_ttl) if remaining_ttl > 0 else None

    @staticmethod
    def is_ttl_expired(enqueued_at: float, original_ttl_seconds: int) -> bool:
        """Check if TTL has expired for a record.

        Args:
            enqueued_at: Timestamp when record was first enqueued
            original_ttl_seconds: Original TTL in seconds

        Returns:
            True if TTL has expired, False otherwise
        """
        if original_ttl_seconds is None:
            return False  # Unlimited TTL never expires

        remaining_ttl = QueueUtils.calculate_remaining_ttl(
            enqueued_at, original_ttl_seconds
        )
        return remaining_ttl is None or remaining_ttl <= 0

    @staticmethod
    def create_queue_result_with_ttl(
        queue_result: "QueueResult", original_ttl_seconds: int | None = None
    ) -> "QueueResult":
        """Create a QueueResult with TTL metadata.

        Args:
            queue_result: Original QueueResult
            original_ttl_seconds: TTL in seconds

        Returns:
            QueueResult with TTL metadata
        """
        if queue_result.original_ttl_seconds is None and original_ttl_seconds is not None:
            queue_result.original_ttl_seconds = original_ttl_seconds
        return queue_result


@dataclass
class QueueResult:
    file: str
    status: QueueResultStatus
    result: Any
    workflow_id: str
    file_content: str
    whisper_hash: str | None = None
    file_execution_id: str | None = None
    enqueued_at: float | None = None
    original_ttl_seconds: int | None = None

    def __post_init__(self):
        """Initialize enqueued_at timestamp if not provided"""
        if self.enqueued_at is None:
            self.enqueued_at = time.time()

    def to_dict(self) -> Any:
        result_dict = {
            "file": self.file,
            "whisper_hash": self.whisper_hash,
            "status": self.status.value,
            "result": self.result,
            "workflow_id": self.workflow_id,
            "file_content": self.file_content,
            "file_execution_id": self.file_execution_id,
            "enqueued_at": self.enqueued_at,
            "original_ttl_seconds": self.original_ttl_seconds,
        }
        return result_dict
