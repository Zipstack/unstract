class RedisSentinelConnectionError(ConnectionError):
    """Raised when Sentinel connection cannot be established after all retries."""

    pass
