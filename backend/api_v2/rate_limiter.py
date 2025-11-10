import logging
import time

from account_v2.models import Organization
from django.conf import settings
from django.core.cache import cache
from django_redis import get_redis_connection

from api_v2.models import OrganizationRateLimit
from api_v2.rate_limit_constants import (
    RateLimitDefaults,
    RateLimitKeys,
)

logger = logging.getLogger(__name__)

redis_cache = get_redis_connection("default")


class APIDeploymentRateLimiter:
    """Rate limiter for API deployment concurrent requests using Redis ZSET with TTL."""

    @classmethod
    def _get_org_key(cls, org_id: str) -> str:
        """Generate Redis key for organization-specific rate limiting."""
        return RateLimitKeys.get_org_executions_key(org_id)

    @classmethod
    def _get_ttl_seconds(cls) -> int:
        """Get TTL in seconds from hours setting."""
        ttl_hours = getattr(
            settings,
            "API_DEPLOYMENT_RATE_LIMIT_TTL_HOURS",
            RateLimitDefaults.DEFAULT_TTL_HOURS,
        )
        return ttl_hours * 3600

    @classmethod
    def _get_cutoff_timestamp(cls) -> float:
        """Get timestamp cutoff for removing stale entries."""
        return time.time() - cls._get_ttl_seconds()

    @classmethod
    def _cleanup_expired_entries(cls, key: str) -> None:
        """Remove entries older than TTL using ZREMRANGEBYSCORE."""
        cutoff = cls._get_cutoff_timestamp()
        redis_cache.zremrangebyscore(key, 0, cutoff)

    @classmethod
    def _get_org_limit(cls, organization: Organization) -> int:
        """Get the concurrent request limit for an organization.

        Uses Django cache framework to avoid DB queries on every request.
        Cache automatically cleared on OrganizationRateLimit save/delete.
        TTL is refreshed on every read to keep frequently-used limits cached.

        Args:
            organization: Organization instance

        Returns:
            Concurrent request limit for the organization
        """
        org_id = str(organization.organization_id)
        cache_key = RateLimitKeys.get_org_limit_cache_key(org_id)
        cache_ttl = getattr(
            settings,
            "API_DEPLOYMENT_RATE_LIMIT_CACHE_TTL",
            RateLimitDefaults.DEFAULT_CACHE_TTL_SECONDS,
        )

        # Try cache first
        cached_limit = cache.get(cache_key)
        if cached_limit is not None:
            # Refresh TTL on cache hit (extends TTL for frequently-used orgs)
            cache.set(cache_key, cached_limit, cache_ttl)
            return cached_limit

        # Cache miss - query DB and cache result
        try:
            org_rate_limit = OrganizationRateLimit.objects.get(organization=organization)
            limit = org_rate_limit.concurrent_request_limit
        except OrganizationRateLimit.DoesNotExist:
            limit = getattr(
                settings,
                "API_DEPLOYMENT_DEFAULT_RATE_LIMIT",
                RateLimitDefaults.DEFAULT_ORG_LIMIT,
            )

        # Cache with TTL
        cache.set(cache_key, limit, cache_ttl)

        return limit

    @classmethod
    def clear_org_limit_cache(cls, org_id: str) -> None:
        """Clear cached rate limit for an organization.

        Args:
            org_id: Organization UUID as string
        """
        cache_key = RateLimitKeys.get_org_limit_cache_key(org_id)
        cache.delete(cache_key)
        logger.info(f"Cleared rate limit cache for org {org_id}")

    @classmethod
    def get_current_usage(cls, organization: Organization) -> dict:
        """Get current usage statistics for an organization.

        Returns:
            dict: {
                'org_count': int - current org-level concurrent requests,
                'global_count': int - current system-wide concurrent requests,
                'org_limit': int - org-level limit,
                'global_limit': int - global limit
            }

        Raises:
            Exception: If Redis operations fail
        """
        org_key = cls._get_org_key(str(organization.organization_id))

        # Cleanup expired entries before counting
        # NOTE: Manual cleanup is required even though ZSET keys have TTL because:
        # 1. Redis TTL expires the entire ZSET key after inactivity, not individual entries
        # 2. Individual ZSET entries remain until the whole key expires
        # 3. Without cleanup, stale entries skew the count and cause incorrect rate limiting
        # 4. ZREMRANGEBYSCORE removes entries older than 6 hours (keeps count accurate)
        # 5. TTL (expire) garbage collects the entire key if org becomes inactive
        # Both mechanisms work together: manual cleanup + key TTL
        cls._cleanup_expired_entries(org_key)
        cls._cleanup_expired_entries(RateLimitKeys.GLOBAL_EXECUTIONS_KEY)

        org_count = redis_cache.zcard(org_key)
        global_count = redis_cache.zcard(RateLimitKeys.GLOBAL_EXECUTIONS_KEY)
        org_limit = cls._get_org_limit(organization)
        global_limit = getattr(
            settings,
            "API_DEPLOYMENT_GLOBAL_RATE_LIMIT",
            RateLimitDefaults.DEFAULT_GLOBAL_LIMIT,
        )

        return {
            "org_count": org_count,
            "global_count": global_count,
            "org_limit": org_limit,
            "global_limit": global_limit,
        }

    @classmethod
    def check_and_acquire(
        cls, organization: Organization, execution_id: str
    ) -> tuple[bool, dict | None]:
        """Atomically check rate limits and acquire slot using per-org Redis lock.

        This implementation uses per-organization locks to prevent race conditions
        within each organization. The global limit is checked but not locked, which
        means under extreme concurrent load across many organizations, the global
        limit may briefly be exceeded by 1-2% before self-correcting.

        Future Enhancement: To strictly enforce global limits without any tolerance,
        add a second lock acquisition for global limit checking:

        ```python
        # After org limit check passes
        from redis.lock import Lock

        global_lock = Lock(
            redis_cache,
            RateLimitKeys.GLOBAL_LOCK_KEY,
            timeout=settings.API_DEPLOYMENT_RATE_LIMIT_LOCK_TIMEOUT,
        )
        try:
            if not global_lock.acquire(blocking=True, blocking_timeout=...):
                return True, None  # Fail open

            # Re-check global limit with lock held
            global_count = redis_cache.zcard(RateLimitKeys.GLOBAL_EXECUTIONS_KEY)
            if global_count >= global_limit:
                return False, {...}

            # Add to both ZSETs while holding global lock
            pipe.zadd(...)
            pipe.execute()
        finally:
            global_lock.release()
        ```

        Args:
            organization: Organization instance
            execution_id: Unique execution identifier to track

        Returns:
            tuple: (can_proceed: bool, limit_info: dict or None)
                If can_proceed is False, limit_info contains details about the exceeded limit
        """
        org_id = str(organization.organization_id)
        org_lock_key = RateLimitKeys.get_org_lock_key(org_id)
        org_key = cls._get_org_key(org_id)
        current_timestamp = time.time()
        cutoff = cls._get_cutoff_timestamp()
        ttl_seconds = cls._get_ttl_seconds()

        from redis.lock import Lock

        lock_timeout = getattr(
            settings,
            "API_DEPLOYMENT_RATE_LIMIT_LOCK_TIMEOUT",
            RateLimitDefaults.DEFAULT_LOCK_TIMEOUT_SECONDS,
        )
        lock_blocking_timeout = getattr(
            settings,
            "API_DEPLOYMENT_RATE_LIMIT_LOCK_BLOCKING_TIMEOUT",
            RateLimitDefaults.DEFAULT_LOCK_BLOCKING_TIMEOUT_SECONDS,
        )

        org_lock = Lock(
            redis_cache,
            org_lock_key,
            timeout=lock_timeout,
            blocking_timeout=lock_blocking_timeout,
        )

        try:
            # Acquire per-organization lock
            acquired = org_lock.acquire(blocking=True)
            if not acquired:
                logger.error(f"Failed to acquire rate limit lock for org {org_id}")
                # Fail open: allow request to proceed
                return True, None

            # Cleanup expired entries
            redis_cache.zremrangebyscore(org_key, 0, cutoff)
            redis_cache.zremrangebyscore(RateLimitKeys.GLOBAL_EXECUTIONS_KEY, 0, cutoff)

            # Check org-level limit
            org_count = redis_cache.zcard(org_key)
            org_limit = cls._get_org_limit(organization)

            if org_count >= org_limit:
                logger.warning(
                    f"Organization {org_id} hit rate limit: {org_count}/{org_limit}"
                )
                return False, {
                    "limit_type": "organization",
                    "current_usage": org_count,
                    "limit": org_limit,
                }

            # Check global limit (no lock - eventual consistency)
            global_count = redis_cache.zcard(RateLimitKeys.GLOBAL_EXECUTIONS_KEY)
            global_limit = getattr(
                settings,
                "API_DEPLOYMENT_GLOBAL_RATE_LIMIT",
                RateLimitDefaults.DEFAULT_GLOBAL_LIMIT,
            )

            if global_count >= global_limit:
                logger.warning(
                    f"Global rate limit exceeded: {global_count}/{global_limit}"
                )
                return False, {
                    "limit_type": "global",
                    "current_usage": global_count,
                    "limit": global_limit,
                }

            # Both checks passed - add to both ZSETs atomically
            pipe = redis_cache.pipeline()
            pipe.zadd(org_key, {execution_id: current_timestamp})
            pipe.expire(org_key, ttl_seconds)
            pipe.zadd(
                RateLimitKeys.GLOBAL_EXECUTIONS_KEY, {execution_id: current_timestamp}
            )
            pipe.expire(RateLimitKeys.GLOBAL_EXECUTIONS_KEY, ttl_seconds)
            pipe.execute()

            logger.info(
                f"Rate limit slot acquired for org {org_id}, execution {execution_id}"
            )
            return True, None

        except Exception as e:
            logger.error(f"Error in rate limit check for org {org_id}: {e}")
            # Fail open: allow request on errors
            return True, None

        finally:
            try:
                org_lock.release()
            except Exception as e:
                # Lock may have already expired or been released
                logger.debug(f"Error releasing lock for org {org_id}: {e}")

    @classmethod
    def check_rate_limit(cls, organization: Organization) -> tuple[bool, dict | None]:
        """Check if a new request can be accepted without exceeding rate limits.

        DEPRECATED: Use check_and_acquire() instead for atomic check-and-acquire.
        This method is kept for backward compatibility but has a race condition.

        Args:
            organization: Organization instance

        Returns:
            tuple: (can_proceed: bool, limit_info: dict or None)
                If can_proceed is False, limit_info contains details about the exceeded limit
        """
        try:
            usage = cls.get_current_usage(organization)

            # Check org-level limit
            if usage["org_count"] >= usage["org_limit"]:
                logger.warning(
                    f"Organization {organization.organization_id} hit rate limit: "
                    f"{usage['org_count']}/{usage['org_limit']}"
                )
                return False, {
                    "limit_type": "organization",
                    "current_usage": usage["org_count"],
                    "limit": usage["org_limit"],
                }

            # Check global limit
            if usage["global_count"] >= usage["global_limit"]:
                logger.warning(
                    f"Global rate limit exceeded: {usage['global_count']}/{usage['global_limit']}"
                )
                return False, {
                    "limit_type": "global",
                    "current_usage": usage["global_count"],
                    "limit": usage["global_limit"],
                }

            return True, None
        except Exception as e:
            # If Redis fails, allow the request to proceed (fail open)
            logger.error(
                f"Rate limit check failed for org {organization.organization_id}: {e}. "
                "Allowing request to proceed."
            )
            return True, None

    @classmethod
    def release_slot(cls, organization_id: str, execution_id: str) -> None:
        """Release a rate limit slot when execution completes.

        Args:
            organization_id: Organization identifier
            execution_id: Execution identifier to release
        """
        org_key = cls._get_org_key(organization_id)

        try:
            # Use pipeline to remove from both keys atomically
            pipe = redis_cache.pipeline()
            pipe.zrem(org_key, execution_id)
            pipe.zrem(RateLimitKeys.GLOBAL_EXECUTIONS_KEY, execution_id)
            pipe.execute()

            logger.debug(
                f"Rate limit slot released for org {organization_id}, execution {execution_id}"
            )
        except Exception as e:
            logger.error(f"Failed to release rate limit slot: {e}")
