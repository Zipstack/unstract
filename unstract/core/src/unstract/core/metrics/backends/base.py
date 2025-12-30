"""Base abstract class for metric backends."""
from abc import ABC, abstractmethod

from ..types import MetricEvent


class AbstractMetricBackend(ABC):
    """Abstract base class for metric recording backends.

    Implementations should handle the actual storage/transmission of metrics.
    """

    @abstractmethod
    def record(self, event: MetricEvent) -> bool:
        """Record a metric event.

        Args:
            event: The MetricEvent to record

        Returns:
            True if the event was recorded successfully, False otherwise
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered events.

        Called periodically or on shutdown to ensure all events are persisted.
        """
        pass

    def close(self) -> None:
        """Clean up resources.

        Called when the backend is no longer needed.
        Default implementation calls flush().
        """
        self.flush()
