"""Cache layer for Dashboard Metrics.

Provides caching for computed metric aggregations to reduce database load.
Uses Redis through Django's cache framework.

Cache TTL Strategy:
- Current hour data: 30 seconds (frequently updating)
- Historical data: 8 hours (stable, rarely changes)
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Cache TTL values (in seconds)
# Time-aware TTLs per documentation
CACHE_TTL_CURRENT_HOUR = 30  # 30 seconds for current hour (updating frequently)
CACHE_TTL_HISTORICAL = 8 * 60 * 60  # 8 hours for historical data (stable)

# Legacy TTLs for compatibility with existing endpoints
CACHE_TTL_OVERVIEW = 60 * 5  # 5 minutes for overview
CACHE_TTL_SUMMARY = 60 * 15  # 15 minutes for summary
CACHE_TTL_SERIES = 60 * 30  # 30 minutes for series data

# Cache key prefixes
CACHE_PREFIX = "dashboard_metrics"


def get_time_aware_cache_ttl(query_end_date: datetime | None = None) -> int:
    """Get appropriate cache TTL based on whether query includes current hour.

    The cache TTL is determined by whether the query timeframe includes
    the current hour (which is still being updated) or only historical
    data (which is stable).

    Args:
        query_end_date: End date of the query timeframe. If None or includes
            the current hour, uses short TTL.

    Returns:
        Cache TTL in seconds
    """
    now = timezone.now()
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)

    # If no end date provided or end date includes current hour, use short TTL
    if query_end_date is None:
        return CACHE_TTL_CURRENT_HOUR

    # Make query_end_date timezone aware if it isn't
    if query_end_date.tzinfo is None:
        query_end_date = timezone.make_aware(query_end_date, timezone.utc)

    # If query includes current hour, use short TTL
    if query_end_date >= current_hour_start:
        return CACHE_TTL_CURRENT_HOUR

    # Historical data only - use long TTL
    return CACHE_TTL_HISTORICAL


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
    }

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            # Get organization from context
            from utils.user_context import UserContext

            org = UserContext.get_organization()
            if not org:
                # No caching without organization context
                return func(self, request, *args, **kwargs)

            org_id = str(org.id)

            # Build cache key from query params
            params = dict(request.query_params.items())
            cache_key = _build_cache_key(org_id, endpoint, params)

            # Check cache
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {endpoint}: {cache_key}")
                from rest_framework.response import Response

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


def invalidate_metrics_cache(org_id: str) -> int:
    """Invalidate all cached metrics for an organization.

    Args:
        org_id: Organization identifier

    Returns:
        Number of keys invalidated
    """
    pattern = f"{CACHE_PREFIX}:{org_id}:*"
    try:
        from utils.cache_service import CacheService

        CacheService.clear_cache(pattern)
        logger.info(f"Invalidated metrics cache for org {org_id}")
        return 1  # Pattern-based delete doesn't return count
    except Exception as e:
        logger.error(f"Failed to invalidate cache for org {org_id}: {e}")
        return 0


class MetricsCacheService:
    """Service class for metrics-specific caching operations."""

    @staticmethod
    def get_cached_overview(org_id: str) -> dict[str, Any] | None:
        """Get cached overview data for an organization."""
        cache_key = _build_cache_key(org_id, "overview", {})
        return cache.get(cache_key)

    @staticmethod
    def set_cached_overview(org_id: str, data: dict[str, Any]) -> None:
        """Set cached overview data for an organization."""
        cache_key = _build_cache_key(org_id, "overview", {})
        cache.set(cache_key, data, CACHE_TTL_OVERVIEW)

    @staticmethod
    def get_cached_summary(
        org_id: str,
        start_date: str,
        end_date: str,
        metric_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Get cached summary data."""
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "metric_name": metric_name,
        }
        cache_key = _build_cache_key(org_id, "summary", params)
        return cache.get(cache_key)

    @staticmethod
    def set_cached_summary(
        org_id: str,
        start_date: str,
        end_date: str,
        data: dict[str, Any],
        metric_name: str | None = None,
    ) -> None:
        """Set cached summary data."""
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "metric_name": metric_name,
        }
        cache_key = _build_cache_key(org_id, "summary", params)
        cache.set(cache_key, data, CACHE_TTL_SUMMARY)

    @staticmethod
    def warm_cache(org_id: str) -> None:
        """Pre-warm cache with commonly accessed data.

        Useful for background tasks to prepare cache after
        new metric data is processed.
        """
        # Import here to avoid circular imports
        from datetime import datetime

        from django.utils import timezone

        from .models import EventMetricsHourly
        from django.db.models import Sum

        try:
            # Warm overview cache
            end_date = timezone.now()
            start_date = end_date - timedelta(days=7)

            overview = (
                EventMetricsHourly.objects.filter(
                    organization_id=org_id,
                    timestamp__gte=start_date,
                    timestamp__lte=end_date,
                )
                .values("metric_name")
                .annotate(
                    total_value=Sum("metric_value"),
                    total_count=Sum("metric_count"),
                )
            )

            MetricsCacheService.set_cached_overview(org_id, list(overview))
            logger.debug(f"Warmed overview cache for org {org_id}")

        except Exception as e:
            logger.warning(f"Failed to warm cache for org {org_id}: {e}")
