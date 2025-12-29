"""Configuration for the metrics module.

Reads environment variables to configure the metric backend.
"""
import logging
import os
from functools import lru_cache

from .backends import AbstractMetricBackend, NoopBackend, QueueBackend

logger = logging.getLogger(__name__)

# Environment variable names
ENV_METRICS_ENABLED = "DASHBOARD_METRICS_ENABLED"
ENV_METRICS_QUEUE = "DASHBOARD_METRICS_QUEUE"
ENV_BROKER_URL = "CELERY_BROKER_URL"


def _str_to_bool(value: str | None) -> bool:
    """Convert string to boolean."""
    if value is None:
        return False
    return value.lower() in ("true", "1", "yes", "on")


@lru_cache(maxsize=1)
def get_backend() -> AbstractMetricBackend:
    """Get the configured metric backend.

    Returns a singleton instance of the appropriate backend based on
    environment configuration.

    Environment Variables:
        DASHBOARD_METRICS_ENABLED: Set to 'true' to enable metrics (default: false)
        DASHBOARD_METRICS_QUEUE: Queue name (default: dashboard_metric_events)
        CELERY_BROKER_URL: RabbitMQ broker URL (required if enabled)

    Returns:
        The configured metric backend instance
    """
    enabled = _str_to_bool(os.getenv(ENV_METRICS_ENABLED))

    if not enabled:
        logger.debug("Dashboard metrics disabled, using NoopBackend")
        return NoopBackend()

    # Get broker URL for queue backend
    broker_url = os.getenv(ENV_BROKER_URL)
    if not broker_url:
        logger.warning(
            f"{ENV_BROKER_URL} not set, metrics will be disabled. "
            f"Set {ENV_BROKER_URL} to enable queue backend."
        )
        return NoopBackend()

    queue_name = os.getenv(ENV_METRICS_QUEUE, "dashboard_metric_events")

    logger.info(
        f"Dashboard metrics enabled with queue backend: {queue_name}"
    )
    return QueueBackend(broker_url=broker_url, queue_name=queue_name)


def reset_backend() -> None:
    """Reset the cached backend instance.

    Useful for testing or when configuration changes.
    """
    get_backend.cache_clear()
