"""Constants and key generators for API deployment rate limiting.

Centralizes all Redis key patterns, cache keys, and configuration constants
to avoid duplication and make maintenance easier.
"""


class RateLimitKeys:
    """Redis key patterns for rate limiting.

    All rate limiting keys follow a consistent naming convention:
    - ZSET keys: api_deployment:rate_limit:{scope}:{id}
    - Lock keys: lock:rate_limit:{scope}:{id}
    - Cache keys: rate_limit:cache:{type}:{id}
    """

    # ZSET keys for tracking active executions
    GLOBAL_EXECUTIONS_KEY = "api_deployment:rate_limit:global"
    ORG_EXECUTIONS_KEY_PATTERN = "api_deployment:rate_limit:org:{org_id}"

    # Lock keys for distributed locking
    GLOBAL_LOCK_KEY = "lock:rate_limit:global"
    ORG_LOCK_KEY_PATTERN = "lock:rate_limit:org:{org_id}"

    # Django cache keys for caching DB values
    ORG_LIMIT_CACHE_KEY_PATTERN = "rate_limit:cache:org_limit:{org_id}"

    @classmethod
    def get_org_executions_key(cls, org_id: str) -> str:
        """Get Redis ZSET key for organization's active executions.

        Args:
            org_id: Organization UUID as string

        Returns:
            Redis key for org's execution ZSET
        """
        return cls.ORG_EXECUTIONS_KEY_PATTERN.format(org_id=org_id)

    @classmethod
    def get_org_lock_key(cls, org_id: str) -> str:
        """Get Redis lock key for organization rate limiting.

        Args:
            org_id: Organization UUID as string

        Returns:
            Redis key for org's distributed lock
        """
        return cls.ORG_LOCK_KEY_PATTERN.format(org_id=org_id)

    @classmethod
    def get_org_limit_cache_key(cls, org_id: str) -> str:
        """Get Django cache key for organization's rate limit value.

        Args:
            org_id: Organization UUID as string

        Returns:
            Django cache key for org's limit
        """
        return cls.ORG_LIMIT_CACHE_KEY_PATTERN.format(org_id=org_id)


class RateLimitDefaults:
    """Default values for rate limiting configuration.

    These are fallback values when settings are not configured.
    Actual values should be set via Django settings / environment variables.
    """

    # Rate limits
    DEFAULT_ORG_LIMIT = 20  # Concurrent requests per organization
    DEFAULT_GLOBAL_LIMIT = 100  # Concurrent requests system-wide

    # TTL and timing
    DEFAULT_TTL_HOURS = 6  # Hours to keep execution in ZSET
    DEFAULT_CACHE_TTL_SECONDS = 600  # 10 minutes cache for org limits

    # Lock timeouts
    DEFAULT_LOCK_TIMEOUT_SECONDS = 2  # Lock auto-expires
    DEFAULT_LOCK_BLOCKING_TIMEOUT_SECONDS = 5  # Wait time to acquire


class RateLimitMessages:
    """User-facing messages for rate limiting.

    Centralized messages for consistency across the application.
    """

    ORG_LIMIT_EXCEEDED_TEMPLATE = (
        "Organization has reached the maximum concurrent API requests limit "
        "({current_usage}/{limit}). Please try again later."
    )

    GLOBAL_LIMIT_EXCEEDED_TEMPLATE = (
        "Our system is currently experiencing high load. "
        "Please try again in a few moments."
    )

    LOCK_ACQUISITION_FAILED = "Failed to acquire rate limit lock. Please try again."

    REDIS_ERROR = "Rate limiting service temporarily unavailable. Request allowed."

    @classmethod
    def get_org_limit_exceeded_message(cls, current_usage: int, limit: int) -> str:
        """Get formatted organization limit exceeded message."""
        return cls.ORG_LIMIT_EXCEEDED_TEMPLATE.format(
            current_usage=current_usage, limit=limit
        )

    @classmethod
    def get_global_limit_exceeded_message(cls) -> str:
        """Get generic global limit exceeded message.

        Returns a user-friendly message without exposing system capacity.
        """
        return cls.GLOBAL_LIMIT_EXCEEDED_TEMPLATE
