"""Cache Key Utilities

Cache key generation and management.
"""


def get_cache_key(pattern: str, **kwargs) -> str:
    """Generate cache key from pattern and parameters."""
    try:
        return pattern.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing parameter for cache key pattern {pattern}: {e}")
