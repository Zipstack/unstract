"""No-op backend that discards all metrics.

Used when metrics recording is disabled (default for OSS).
"""

import logging

from ..types import MetricEvent
from .base import AbstractMetricBackend

logger = logging.getLogger(__name__)


class NoopBackend(AbstractMetricBackend):
    """Backend that discards all metrics.

    Used when DASHBOARD_METRICS_ENABLED is False.
    This is the default for OSS installations.
    """

    def __init__(self) -> None:
        """Initialize the no-op backend."""
        self._logged_once = False

    def record(self, event: MetricEvent) -> bool:
        """Discard the metric event.

        Args:
            event: The MetricEvent to discard

        Returns:
            True (always succeeds since nothing is stored)
        """
        if not self._logged_once:
            logger.debug(
                "Metrics recording is disabled. "
                "Set DASHBOARD_METRICS_ENABLED=true to enable."
            )
            self._logged_once = True
        return True

    def flush(self) -> None:
        """No-op flush."""
        pass
