"""Cache Configuration Constants

Redis cache configuration and patterns.
"""


class CacheConfig:
    """Redis cache configuration and patterns."""

    # Cache key patterns
    EXECUTION_STATUS_PATTERN = "exec_status:{org_id}:{execution_id}"
    PIPELINE_STATUS_PATTERN = "pipeline_status:{org_id}:{pipeline_id}"
    BATCH_SUMMARY_PATTERN = "batch_summary:{org_id}:{execution_id}"
    CALLBACK_ATTEMPTS_PATTERN = "callback_attempts:{org_id}:{execution_id}"
    BACKOFF_ATTEMPTS_PATTERN = "backoff_attempts:{org_id}:{execution_id}:{operation}"
    CIRCUIT_BREAKER_PATTERN = "circuit_breaker:{service}:{operation}"

    # TTL values (in seconds)
    EXECUTION_STATUS_TTL = 60
    PIPELINE_STATUS_TTL = 120
    BATCH_SUMMARY_TTL = 90
    CALLBACK_ATTEMPTS_TTL = 3600  # 1 hour
    BACKOFF_ATTEMPTS_TTL = 1800  # 30 minutes
    CIRCUIT_BREAKER_TTL = 300  # 5 minutes

    # Cache validation settings
    MAX_CACHE_AGE = 300  # 5 minutes absolute max
    STALE_DATA_THRESHOLD = 120  # 2 minutes

    # Connection settings
    REDIS_SOCKET_TIMEOUT = 5
    REDIS_SOCKET_CONNECT_TIMEOUT = 5
    REDIS_HEALTH_CHECK_INTERVAL = 30
