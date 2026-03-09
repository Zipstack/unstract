class RedisSentinelConnectionError(Exception):
    """Raised when Sentinel connection cannot be established after all retries."""

    pass
