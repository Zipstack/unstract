from django.conf import settings
from utils.cache_service import CacheService

from workflow_manager.execution.dto import ExecutionCache, ExecutionCacheFields
from workflow_manager.workflow_v2.enums import ExecutionStatus


class ExecutionCacheUtils:
    expire_time = int(settings.EXECUTION_CACHE_EXPIRE_TIME)

    @staticmethod
    def _get_execution_cache_key(workflow_id: str, execution_id: str) -> str:
        """Get Redis cache key for file_execution."""
        return f"execution:{workflow_id}:{execution_id}"

    @classmethod
    def get_execution(cls, workflow_id: str, execution_id: str) -> ExecutionCache | None:
        """Get or create file execution."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        execution = CacheService.hgetall(cache_key)
        if execution:
            # Decode keys and values from bytes to strings
            decoded = {k.decode(): v.decode() for k, v in execution.items()}
            return ExecutionCache(**decoded)
        else:
            return None

    @classmethod
    def is_execution_exists(cls, workflow_id: str, execution_id: str) -> bool:
        """Check if file execution exists."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        return CacheService.check_a_key_exist(cache_key)

    @classmethod
    def create_execution(cls, execution: ExecutionCache) -> None:
        """Create file execution."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=execution.workflow_id, execution_id=execution.execution_id
        )
        CacheService.hset(
            cache_key, mapping=execution.to_json(), expire_time=cls.expire_time
        )

    @classmethod
    def update_status(
        cls, workflow_id: str, execution_id: str, status: ExecutionStatus
    ) -> None:
        """Update file execution."""
        try:
            status_enum = ExecutionStatus(status)
        except ValueError:
            raise ValueError(
                f"Invalid status: {status}. Must be a valid ExecutionStatus."
            )
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.hset(
            cache_key,
            field=ExecutionCacheFields.STATUS,
            value=status_enum.value,
            expire_time=cls.expire_time,
        )

    @classmethod
    def increment_completed_files(cls, workflow_id: str, execution_id: str) -> None:
        """Increment completed files."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.hincrby(cache_key, ExecutionCacheFields.COMPLETED_FILES, 1)

    @classmethod
    def increment_failed_files(cls, workflow_id: str, execution_id: str) -> None:
        """Increment failed files."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.hincrby(cache_key, ExecutionCacheFields.FAILED_FILES, 1)

    @classmethod
    def delete_execution(cls, workflow_id: str, execution_id: str) -> None:
        """Delete file execution."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.delete_a_key(cache_key)
