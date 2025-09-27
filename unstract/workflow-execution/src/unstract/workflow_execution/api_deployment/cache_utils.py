"""Worker result caching utilities matching backend ResultCacheUtils pattern."""

import json
import logging
import os
from typing import Any

import redis

from unstract.core.worker_models import FileExecutionResult

logger = logging.getLogger(__name__)


class WorkerResultCacheUtils:
    """Worker result caching utilities matching backend ResultCacheUtils pattern."""

    def __init__(self):
        self.expire_time = int(
            os.getenv("EXECUTION_RESULT_TTL_SECONDS", "86400")
        )  # 24 hours default
        self._redis_client = None

    def _get_redis_client(self):
        """Get Redis client instance."""
        if self._redis_client is None:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db = int(os.getenv("REDIS_DB", "0"))

            self._redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=False,  # Keep binary for JSON handling
                socket_connect_timeout=5,
                socket_timeout=5,
            )

        return self._redis_client

    def check_redis_health(self, timeout_seconds: float = 2.0) -> bool:
        """Check if Redis is healthy and accessible."""
        try:
            redis_client = self._get_redis_client()
            redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            raise

    def _get_api_results_cache_key(self, workflow_id: str, execution_id: str) -> str:
        """Get Redis cache key for api_results matching backend pattern."""
        return f"api_results:{workflow_id}:{execution_id}"

    def update_api_results(
        self, workflow_id: str, execution_id: str, api_result: FileExecutionResult
    ) -> None:
        """Update api_results in Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()

            # Convert result to JSON string (matching backend CacheService.rpush_with_expire)
            result_json = json.dumps(api_result.to_json())

            # Use Redis pipeline for atomic operation
            pipe = redis_client.pipeline()
            pipe.rpush(cache_key, result_json)
            pipe.expire(cache_key, self.expire_time)
            pipe.execute()

            logger.info(f"Successfully cached API result for execution {execution_id}")

        except Exception as e:
            logger.error(f"Failed to cache API result for execution {execution_id}: {e}")
            # Re-raise to ensure caching failures are visible (fail-fast approach)
            raise

    def get_api_results(self, workflow_id: str, execution_id: str) -> list:
        """Get api_results from Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()

            # Get all results from Redis list
            result_strings = redis_client.lrange(cache_key, 0, -1)

            # Convert back to dictionaries
            results = []
            for result_string in result_strings:
                try:
                    result_dict = json.loads(result_string.decode("utf-8"))
                    results.append(result_dict)
                except Exception as parse_error:
                    logger.error(f"Failed to parse cached result: {parse_error}")
                    continue

            return results

        except Exception as e:
            logger.error(
                f"Failed to retrieve API results for execution {execution_id}: {e}"
            )
            return []

    def delete_api_results(self, workflow_id: str, execution_id: str) -> None:
        """Delete api_results from Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()
            redis_client.delete(cache_key)

        except Exception as e:
            logger.error(
                f"Failed to delete API results for execution {execution_id}: {e}"
            )

    @staticmethod
    def get_cached_result(cache_key: str) -> Any:
        """Get cached result (legacy method)."""
        return None

    @staticmethod
    def cache_result(cache_key: str, result: Any) -> bool:
        """Cache result (legacy method)."""
        return True
