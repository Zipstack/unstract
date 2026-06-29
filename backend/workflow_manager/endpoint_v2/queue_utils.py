import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from django.conf import settings
from unstract.connectors.queues import connectors as queue_connectors
from unstract.connectors.queues.unstract_queue import UnstractQueue
from utils.constants import Common
from workflow_manager.endpoint_v2.exceptions import UnstractQueueException

logger = logging.getLogger(__name__)


class QueueResultStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    # Add other statuses as needed


class QueueUtils:
    # HITL connectors registry (lazy-loaded to avoid circular imports)
    _hitl_connectors = {}

    @staticmethod
    def get_queue_inst(connector_settings: dict[str, Any] = {}) -> UnstractQueue:
        """Get queue connector instance based on configuration.

        For HITL operations, this can return PostgreSQL, Hybrid, or Redis connectors
        based on the HITL_QUEUE_BACKEND setting.
        """
        # Check if caller explicitly wants the default (non-HITL) backend
        # This is used by HybridQueue to get the actual Redis connector without recursion
        force_default = connector_settings.get("force_default_backend", False)
        if force_default:
            # Strip the flag and return default Redis connector
            clean_settings = {
                k: v
                for k, v in connector_settings.items()
                if k != "force_default_backend"
            }
            if not queue_connectors:
                raise UnstractQueueException(detail="Queue connector not exists")
            queue_connector_key = next(iter(queue_connectors))
            connector = queue_connectors[queue_connector_key][Common.METADATA][
                Common.CONNECTOR
            ]
            return connector(clean_settings)

        # Check if this is for HITL operations
        is_hitl = connector_settings.get("use_hitl_backend", False)

        # Auto-detect HITL backend if HITL_QUEUE_BACKEND is set to hybrid/postgresql
        hitl_backend = getattr(settings, "HITL_QUEUE_BACKEND", "redis")
        if not is_hitl and hitl_backend in ("hybrid", "postgresql"):
            is_hitl = True

        if is_hitl:
            # Use HITL-specific queue backend
            return QueueUtils.get_hitl_queue_inst(hitl_backend, connector_settings)

        # Default behavior for non-HITL operations
        if not queue_connectors:
            raise UnstractQueueException(detail="Queue connector not exists")
        queue_connector_key = next(iter(queue_connectors))
        connector = queue_connectors[queue_connector_key][Common.METADATA][
            Common.CONNECTOR
        ]
        connector_class: UnstractQueue = connector(connector_settings)
        return connector_class

    @staticmethod
    def get_hitl_queue_inst(
        backend: str, connector_settings: dict[str, Any] = {}
    ) -> UnstractQueue:
        """Get HITL-specific queue connector instance with dynamic imports.

        This method uses dynamic imports to avoid hard dependencies on the
        manual_review_v2 pluggable app, allowing graceful degradation when
        the app is not available.

        Args:
            backend: Backend type ('postgresql', 'hybrid', 'redis')
            connector_settings: Connector configuration

        Returns:
            Configured queue connector instance

        Raises:
            UnstractQueueException: When HITL connectors are not available
        """
        # For Redis backend, use default connector
        if backend == "redis":
            # Strip HITL flag to force default (non-HITL) connector path
            non_hitl_settings = dict(connector_settings)
            non_hitl_settings.pop("use_hitl_backend", None)
            return QueueUtils.get_queue_inst(non_hitl_settings)

        # For PostgreSQL and Hybrid backends, try dynamic imports
        try:
            if backend == "postgresql":
                connector_class = QueueUtils._import_hitl_connector("PostgreSQLQueue")
                return connector_class(connector_settings)

            elif backend == "hybrid":
                connector_class = QueueUtils._import_hitl_connector("HybridQueue")
                return connector_class(connector_settings)

            else:
                logger.warning(
                    f"Unknown HITL queue backend '{backend}'. "
                    f"Valid options: postgresql, hybrid, redis. "
                    f"Attempting fallback to hybrid."
                )
                connector_class = QueueUtils._import_hitl_connector("HybridQueue")
                return connector_class(connector_settings)

        except ImportError as e:
            logger.error(
                f"HITL queue backend '{backend}' not available: {e}. "
                f"Make sure 'pluggable_apps.manual_review_v2' is installed and configured."
            )
            raise UnstractQueueException(
                detail=f"HITL queue backend '{backend}' not available. "
                f"Please install the manual_review_v2 app or use 'redis' backend."
            )
        except Exception as e:
            logger.error(f"Failed to initialize HITL queue backend '{backend}': {e}")
            raise UnstractQueueException(
                detail=f"Failed to initialize HITL queue backend '{backend}': {str(e)}"
            )

    @classmethod
    def _import_hitl_connector(cls, connector_name: str):
        """Get HITL connector class from registry (lazy-loaded to avoid circular imports).

        Args:
            connector_name: Name of the connector class to get

        Returns:
            The connector class

        Raises:
            ImportError: When the connector is not available
        """
        # Lazy initialization on first access (avoids circular imports)
        if not cls._hitl_connectors:
            try:
                from pluggable_apps.manual_review_v2.connectors import (
                    HybridQueue,
                    PostgreSQLQueue,
                )

                cls._hitl_connectors = {
                    "PostgreSQLQueue": PostgreSQLQueue,
                    "HybridQueue": HybridQueue,
                }
            except ImportError as e:
                logger.debug(f"HITL connectors not available: {e}")

        if not cls._hitl_connectors:
            raise ImportError(
                "HITL connectors not available. Make sure 'pluggable_apps.manual_review_v2' is installed."
            )

        if connector_name not in cls._hitl_connectors:
            available_connectors = list(cls._hitl_connectors.keys())
            raise ImportError(
                f"Unknown HITL connector: {connector_name}. Available: {available_connectors}"
            )

        return cls._hitl_connectors[connector_name]

    @staticmethod
    def calculate_remaining_ttl(enqueued_at: float, ttl_seconds: int) -> int | None:
        """Calculate remaining TTL based on original enqueue time and TTL.

        Args:
            enqueued_at: Timestamp when record was first enqueued
            ttl_seconds: TTL in seconds

        Returns:
            Remaining TTL in seconds, or None if expired
        """
        if ttl_seconds is None:
            return None  # Unlimited TTL

        current_time = time.time()
        elapsed_time = current_time - enqueued_at
        remaining_ttl = ttl_seconds - int(elapsed_time)

        return max(0, remaining_ttl) if remaining_ttl > 0 else None

    @staticmethod
    def is_ttl_expired(enqueued_at: float, ttl_seconds: int) -> bool:
        """Check if TTL has expired for a record.

        Args:
            enqueued_at: Timestamp when record was first enqueued
            ttl_seconds: TTL in seconds

        Returns:
            True if TTL has expired, False otherwise
        """
        if ttl_seconds is None:
            return False  # Unlimited TTL never expires

        remaining_ttl = QueueUtils.calculate_remaining_ttl(enqueued_at, ttl_seconds)
        return remaining_ttl is None or remaining_ttl <= 0

    @staticmethod
    def create_queue_result_with_ttl(
        queue_result: "QueueResult", ttl_seconds: int | None = None
    ) -> "QueueResult":
        """Create a QueueResult with TTL metadata.

        Args:
            queue_result: Original QueueResult
            ttl_seconds: TTL in seconds

        Returns:
            QueueResult with TTL metadata
        """
        if queue_result.ttl_seconds is None and ttl_seconds is not None:
            queue_result.ttl_seconds = ttl_seconds
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
    ttl_seconds: int | None = None
    extracted_text: str | None = None
    hitl_reason: str | None = None

    def __post_init__(self):
        """Initialize enqueued_at timestamp if not provided and validate required fields"""
        if self.enqueued_at is None:
            self.enqueued_at = time.time()

        # Validate required fields
        if not self.file:
            raise ValueError("QueueResult requires a valid file name")
        if not self.workflow_id:
            raise ValueError("QueueResult requires a valid workflow_id")
        if self.status is None:
            raise ValueError("QueueResult requires a valid status")

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
            "ttl_seconds": self.ttl_seconds,
            "extracted_text": self.extracted_text,
            "hitl_reason": self.hitl_reason,
        }
        return result_dict
