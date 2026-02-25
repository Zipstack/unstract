"""Cache layer for Dashboard Metrics.

Provides caching for computed metric aggregations to reduce database load.
Uses Redis through Django's cache framework.

Cache TTL Strategy:
- Current hour/day/month data: Configurable via DASHBOARD_CACHE_TTL_CURRENT_BUCKET (default 60s)
- Historical data: Configurable via DASHBOARD_CACHE_TTL_HISTORICAL (default 8 hours)

Bucket-based Caching:
- Time ranges are split into buckets (hourly/daily/monthly)
- Each bucket is cached independently with appropriate TTL
- MGET used to fetch multiple buckets in single Redis round-trip
- Partial cache hits allow reuse across overlapping queries
"""

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response
from utils.user_context import UserContext

logger = logging.getLogger(__name__)

# Try to get raw Redis client for MGET/pipeline operations
try:
    from django_redis import get_redis_connection

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("django_redis not available, bucket caching will use fallback")

# Cache TTL values from Django settings (configured in settings/base.py)
CACHE_TTL_CURRENT_BUCKET = settings.DASHBOARD_CACHE_TTL_CURRENT_BUCKET
CACHE_TTL_HISTORICAL = settings.DASHBOARD_CACHE_TTL_HISTORICAL
CACHE_TTL_OVERVIEW = settings.DASHBOARD_CACHE_TTL_OVERVIEW
CACHE_TTL_SUMMARY = settings.DASHBOARD_CACHE_TTL_SUMMARY
CACHE_TTL_SERIES = settings.DASHBOARD_CACHE_TTL_SERIES
CACHE_TTL_WORKFLOW_USAGE = settings.DASHBOARD_CACHE_TTL_WORKFLOW_USAGE

# Cache key prefix
CACHE_PREFIX = "dashboard_metrics"


def _build_cache_key(org_id: str, endpoint: str, params: dict[str, Any]) -> str:
    """Build a unique cache key from organization, endpoint, and parameters.

    Args:
        org_id: Organization identifier
        endpoint: API endpoint name (e.g., 'summary', 'series')
        params: Query parameters

    Returns:
        Unique cache key string
    """
    # Sort params for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:12]
    return f"{CACHE_PREFIX}:{org_id}:{endpoint}:{params_hash}"


def cache_metrics_response(
    endpoint: str,
    ttl: int | None = None,
) -> Callable:
    """Decorator to cache metrics API responses.

    Args:
        endpoint: Endpoint name for cache key
        ttl: Cache TTL in seconds (defaults based on endpoint)

    Returns:
        Decorated function with caching
    """
    # Default TTLs per endpoint
    default_ttls = {
        "overview": CACHE_TTL_OVERVIEW,
        "summary": CACHE_TTL_SUMMARY,
        "series": CACHE_TTL_SERIES,
        "workflow_token_usage": CACHE_TTL_WORKFLOW_USAGE,
        "recent_activity": CACHE_TTL_OVERVIEW,
    }

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            # Get organization from context
            org = UserContext.get_organization()
            if not org:
                # No caching without organization context
                return func(self, request, *args, **kwargs)

            org_id = str(org.id)

            # Build cache key from query params (exclude refresh param)
            params = {k: v for k, v in request.query_params.items() if k != "refresh"}
            cache_key = _build_cache_key(org_id, endpoint, params)

            # Skip cache if refresh=true requested
            force_refresh = request.query_params.get("refresh", "").lower() == "true"

            # Check cache (unless force refresh)
            if not force_refresh:
                cached = cache.get(cache_key)
                if cached is not None:
                    logger.debug(f"Cache hit for {endpoint}: {cache_key}")
                    return Response(cached)

            # Execute function and cache result
            response = func(self, request, *args, **kwargs)

            if response.status_code == 200:
                cache_ttl = ttl or default_ttls.get(endpoint, CACHE_TTL_SUMMARY)
                cache.set(cache_key, response.data, cache_ttl)
                logger.debug(f"Cached {endpoint} for {cache_ttl}s: {cache_key}")

            return response

        return wrapper

    return decorator


# =============================================================================
# Bucket-based Caching for Time-Range Queries
# =============================================================================


def _get_redis_client():
    """Get raw Redis client for MGET/pipeline operations.

    Returns:
        Redis client or None if not available
    """
    if not REDIS_AVAILABLE:
        return None
    try:
        return get_redis_connection("default")
    except Exception:
        logger.warning("Failed to get Redis connection")
        return None


def generate_time_buckets(
    start_date: datetime,
    end_date: datetime,
    granularity: str = "hourly",
) -> list[datetime]:
    """Generate time bucket timestamps for a date range.

    Args:
        start_date: Start of the range
        end_date: End of the range
        granularity: 'hourly', 'daily', or 'monthly'

    Returns:
        List of bucket start timestamps
    """
    buckets = []

    # Ensure timezone awareness
    if start_date.tzinfo is None:
        start_date = timezone.make_aware(start_date, timezone.utc)
    if end_date.tzinfo is None:
        end_date = timezone.make_aware(end_date, timezone.utc)

    if granularity == "hourly":
        # Truncate to hour
        current = start_date.replace(minute=0, second=0, microsecond=0)
        while current <= end_date:
            buckets.append(current)
            current = current + timedelta(hours=1)

    elif granularity == "daily":
        # Truncate to day
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            buckets.append(current)
            current = current + timedelta(days=1)

    elif granularity == "monthly":
        # Truncate to first of month
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current <= end_date:
            buckets.append(current)
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return buckets


def _build_bucket_key(
    org_id: str,
    granularity: str,
    bucket_ts: datetime,
    metric_name: str | None = None,
) -> str:
    """Build cache key for a specific time bucket.

    Key format: metrics:bucket:<granularity>:<org_id>:<bucket_iso>[:metric_name]

    Args:
        org_id: Organization identifier
        granularity: 'hourly', 'daily', or 'monthly'
        bucket_ts: Bucket timestamp
        metric_name: Optional metric name filter

    Returns:
        Cache key string
    """
    bucket_str = (
        bucket_ts.strftime("%Y-%m-%dT%H:00:00")
        if granularity == "hourly"
        else bucket_ts.strftime("%Y-%m-%d")
        if granularity == "daily"
        else bucket_ts.strftime("%Y-%m")
    )

    key = f"{CACHE_PREFIX}:bucket:{granularity}:{org_id}:{bucket_str}"
    if metric_name:
        key = f"{key}:{metric_name}"
    return key


def _get_ttl_for_bucket(bucket_ts: datetime, granularity: str = "hourly") -> int:
    """Get appropriate TTL for a time bucket.

    Current period uses short TTL (30s), historical uses long TTL (8h).

    Args:
        bucket_ts: Bucket timestamp
        granularity: 'hourly', 'daily', or 'monthly'

    Returns:
        TTL in seconds
    """
    now = timezone.now()

    if granularity == "hourly":
        current_bucket = now.replace(minute=0, second=0, microsecond=0)
    elif granularity == "daily":
        current_bucket = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        current_bucket = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Ensure bucket_ts is timezone aware for comparison
    if bucket_ts.tzinfo is None:
        bucket_ts = timezone.make_aware(bucket_ts, timezone.utc)

    # Current bucket gets short TTL, historical gets long TTL
    if bucket_ts >= current_bucket:
        return CACHE_TTL_CURRENT_BUCKET
    return CACHE_TTL_HISTORICAL


def mget_metrics_buckets(
    org_id: str,
    start_date: datetime,
    end_date: datetime,
    granularity: str = "hourly",
    metric_name: str | None = None,
) -> tuple[dict[datetime, list[dict]], list[datetime]]:
    """Batch fetch cached metrics using Redis MGET.

    Args:
        org_id: Organization identifier
        start_date: Start of date range
        end_date: End of date range
        granularity: 'hourly', 'daily', or 'monthly'
        metric_name: Optional metric name filter

    Returns:
        Tuple of (cached_data dict, missing_buckets list)
        - cached_data: {bucket_timestamp: [records]}
        - missing_buckets: list of bucket timestamps not in cache
    """
    buckets = generate_time_buckets(start_date, end_date, granularity)

    if not buckets:
        return {}, []

    redis_client = _get_redis_client()

    # Fallback to individual cache.get if Redis MGET not available
    if not redis_client:
        cached_data = {}
        missing_buckets = []

        for bucket_ts in buckets:
            key = _build_bucket_key(org_id, granularity, bucket_ts, metric_name)
            data = cache.get(key)
            if data is not None:
                cached_data[bucket_ts] = data
            else:
                missing_buckets.append(bucket_ts)

        logger.debug(
            f"Bucket cache (fallback): {len(cached_data)} hits, "
            f"{len(missing_buckets)} misses for org {org_id}"
        )
        return cached_data, missing_buckets

    # Use Redis MGET for batch retrieval
    keys = [
        _build_bucket_key(org_id, granularity, bucket_ts, metric_name)
        for bucket_ts in buckets
    ]

    try:
        # MGET returns list of values (or None for missing keys)
        values = redis_client.mget(keys)

        cached_data = {}
        missing_buckets = []

        for bucket_ts, value in zip(buckets, values, strict=False):
            if value is not None:
                try:
                    cached_data[bucket_ts] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    missing_buckets.append(bucket_ts)
            else:
                missing_buckets.append(bucket_ts)

        logger.debug(
            f"Bucket cache (MGET): {len(cached_data)} hits, "
            f"{len(missing_buckets)} misses for org {org_id}"
        )
        return cached_data, missing_buckets

    except Exception:
        logger.exception("MGET failed, falling back to no cache")
        return {}, buckets


def mset_metrics_buckets(
    org_id: str,
    bucket_data: dict[datetime, list[dict]],
    granularity: str = "hourly",
    metric_name: str | None = None,
) -> int:
    """Batch save metrics buckets to cache using Redis pipeline.

    Each bucket gets TTL based on whether it's current or historical.

    Args:
        org_id: Organization identifier
        bucket_data: Dict of {bucket_timestamp: [records]}
        granularity: 'hourly', 'daily', or 'monthly'
        metric_name: Optional metric name filter

    Returns:
        Number of buckets saved
    """
    if not bucket_data:
        return 0

    redis_client = _get_redis_client()

    # Fallback to individual cache.set if Redis pipeline not available
    if not redis_client:
        saved = 0
        for bucket_ts, data in bucket_data.items():
            key = _build_bucket_key(org_id, granularity, bucket_ts, metric_name)
            ttl = _get_ttl_for_bucket(bucket_ts, granularity)
            try:
                cache.set(key, data, ttl)
                saved += 1
            except Exception:
                logger.warning(f"Failed to cache bucket {key}")
        return saved

    # Use Redis pipeline for batch save with different TTLs
    try:
        pipe = redis_client.pipeline()

        for bucket_ts, data in bucket_data.items():
            key = _build_bucket_key(org_id, granularity, bucket_ts, metric_name)
            ttl = _get_ttl_for_bucket(bucket_ts, granularity)
            serialized = json.dumps(data, default=str)
            pipe.setex(key, ttl, serialized)

        pipe.execute()

        logger.debug(
            f"Cached {len(bucket_data)} buckets for org {org_id} "
            f"(granularity={granularity})"
        )
        return len(bucket_data)

    except Exception:
        logger.exception("Pipeline MSET failed")
        return 0
