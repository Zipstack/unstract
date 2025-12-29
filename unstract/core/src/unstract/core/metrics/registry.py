"""Metric registry for validation and type lookup."""
import logging
from typing import Set

from .types import MetricName, MetricType, METRIC_TYPE_MAP

logger = logging.getLogger(__name__)

# Set of valid metric names for fast lookup
_REGISTERED_METRICS: Set[str] = {m.value for m in MetricName}


def validate_metric(metric_name: str) -> bool:
    """Check if a metric name is registered.

    Args:
        metric_name: The metric name to validate

    Returns:
        True if the metric is registered, False otherwise
    """
    return metric_name in _REGISTERED_METRICS


def get_metric_type(metric_name: str) -> MetricType:
    """Get the type of a metric.

    Args:
        metric_name: The metric name to look up

    Returns:
        The MetricType for the given metric

    Raises:
        ValueError: If the metric is not registered
    """
    if not validate_metric(metric_name):
        raise ValueError(f"Unknown metric: {metric_name}")
    return METRIC_TYPE_MAP[metric_name]


def get_all_metrics() -> list[str]:
    """Get all registered metric names.

    Returns:
        List of all registered metric names
    """
    return list(_REGISTERED_METRICS)


def get_metrics_by_type(metric_type: MetricType) -> list[str]:
    """Get all metrics of a specific type.

    Args:
        metric_type: The type of metrics to retrieve

    Returns:
        List of metric names matching the specified type
    """
    return [
        name for name, mtype in METRIC_TYPE_MAP.items() if mtype == metric_type
    ]
