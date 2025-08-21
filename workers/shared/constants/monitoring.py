"""Monitoring Configuration Constants

Monitoring and metrics configuration.
"""


class MonitoringConfig:
    """Monitoring and metrics configuration."""

    # Metric collection intervals
    TASK_METRICS_INTERVAL = 10  # 10 seconds
    WORKER_METRICS_INTERVAL = 30  # 30 seconds
    HEALTH_CHECK_INTERVAL = 60  # 1 minute

    # Performance thresholds
    TASK_SLOW_THRESHOLD = 30.0  # 30 seconds
    MEMORY_WARNING_THRESHOLD = 80  # 80% of max memory
    ERROR_RATE_WARNING_THRESHOLD = 5.0  # 5% error rate

    # Metric retention periods
    TASK_METRICS_RETENTION = 3600  # 1 hour
    WORKER_METRICS_RETENTION = 86400  # 24 hours
    ERROR_METRICS_RETENTION = 604800  # 7 days

    # Alert thresholds
    CONSECUTIVE_FAILURES_ALERT = 5
    HIGH_ERROR_RATE_ALERT = 10.0  # 10%
    MEMORY_CRITICAL_ALERT = 95  # 95%
