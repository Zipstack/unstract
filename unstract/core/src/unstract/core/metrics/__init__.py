"""Unstract Core Metrics Module.

Framework-agnostic metrics recording for all Unstract services.
Supports multiple backends (queue, observability) configurable via environment.

Usage:
    from unstract.core.metrics import record, MetricName

    # Record a counter metric
    record(
        org_id="org-123",
        metric_name=MetricName.DOCUMENTS_PROCESSED,
        metric_value=1,
        labels={"source": "s3"},
        project="my-project",
    )

    # Record a histogram metric (latency)
    record(
        org_id="org-123",
        metric_name=MetricName.DEPLOYED_API_REQUESTS,
        metric_value=150.5,  # milliseconds
        labels={"endpoint": "/api/extract", "status": "success"},
        project="my-project",
    )

Environment Variables:
    DASHBOARD_METRICS_ENABLED: Set to 'true' to enable metrics (default: false)
    DASHBOARD_METRICS_QUEUE: Queue name (default: dashboard_metric_events)
    CELERY_BROKER_URL: RabbitMQ broker URL (required if enabled)
"""
import logging

from .types import MetricEvent, MetricName, MetricType
from .registry import validate_metric, get_metric_type, get_all_metrics
from .config import get_backend, reset_backend

__all__ = [
    # Public API
    "record",
    # Types
    "MetricEvent",
    "MetricName",
    "MetricType",
    # Registry
    "validate_metric",
    "get_metric_type",
    "get_all_metrics",
    # Config
    "get_backend",
    "reset_backend",
]

logger = logging.getLogger(__name__)


def record(
    org_id: str,
    metric_name: str | MetricName,
    metric_value: int | float,
    labels: dict[str, str] | None = None,
    project: str | None = None,
    tag: str | None = None,
) -> bool:
    """Record a metric event.

    This is the main entry point for recording metrics from any Unstract service.
    The metric is validated against the registry and sent to the configured backend.

    Args:
        org_id: Organization identifier
        metric_name: Name of the metric (from MetricName enum or string)
        metric_value: Numeric value (int for counters, float for histograms)
        labels: Optional dimensional labels for filtering/grouping
        project: Project identifier (default: "default")
        tag: Optional tag for categorization

    Returns:
        True if the metric was recorded successfully, False otherwise

    Example:
        >>> from unstract.core.metrics import record, MetricName
        >>> record(
        ...     org_id="org-123",
        ...     metric_name=MetricName.DOCUMENTS_PROCESSED,
        ...     metric_value=1,
        ...     labels={"source": "s3"},
        ...     project="my-project",
        ... )
        True
    """
    # Convert enum to string if needed
    if isinstance(metric_name, MetricName):
        metric_name = metric_name.value

    # Validate metric name
    if not validate_metric(metric_name):
        logger.warning(f"Unknown metric: {metric_name}. Skipping.")
        return False

    # Create metric event
    try:
        event = MetricEvent(
            org_id=org_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_type=get_metric_type(metric_name),
            labels=labels or {},
            project=project or "default",
            tag=tag,
        )
    except Exception as e:
        logger.error(f"Failed to create metric event: {e}")
        return False

    # Record to backend
    backend = get_backend()
    return backend.record(event)
