from typing import Any

from django.conf import settings
from utils.cache_service import CacheService
from workflow_manager.endpoint_v2.dto import FileExecutionResult


class ResultCacheUtils:
    expire_time = int(settings.EXECUTION_RESULT_TTL_SECONDS)

    @staticmethod
    def _get_api_results_cache_key(workflow_id: str, execution_id: str) -> str:
        """Get Redis cache key for api_results."""
        return f"api_results:{workflow_id}:{execution_id}"

    @classmethod
    def get_api_results(cls, workflow_id: str, execution_id: str) -> list[dict[str, Any]]:
        """Get api_results from Redis cache."""
        cache_key = cls._get_api_results_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        return CacheService.lrange_json(cache_key)

    @classmethod
    def update_api_results(
        cls, workflow_id: str, execution_id: str, api_result: FileExecutionResult
    ) -> None:
        """Update api_results in Redis cache."""
        cache_key = cls._get_api_results_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.rpush_with_expire(cache_key, api_result.to_json(), cls.expire_time)

    @classmethod
    def delete_api_results(cls, workflow_id: str, execution_id: str) -> None:
        """Delete api_results from Redis cache."""
        cache_key = cls._get_api_results_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.delete_a_key(cache_key)
