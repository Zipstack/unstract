from typing import Any

from django.conf import settings
from utils.cache_service import CacheService

from workflow_manager.execution.dto import ExecutionCache, ExecutionCacheFields
from workflow_manager.workflow_v2.enums import ExecutionStatus


class ExecutionCacheUtils:
    """Utility class for accessing and managing workflow execution status and
    related information from cache to reduce database load.
    """

    expire_time = int(settings.EXECUTION_CACHE_TTL_SECONDS)

    @staticmethod
    def _get_execution_cache_key(workflow_id: str, execution_id: str) -> str:
        """Get Redis cache key for execution."""
        return f"execution:{workflow_id}:{execution_id}"

    @classmethod
    def get_execution(cls, workflow_id: str, execution_id: str) -> ExecutionCache | None:
        """Get or create execution."""
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
        """Check if execution exists."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        return CacheService.check_a_key_exist(cache_key)

    @classmethod
    def create_execution(cls, execution: ExecutionCache) -> None:
        """Create execution."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=execution.workflow_id, execution_id=execution.execution_id
        )
        CacheService.hset(
            cache_key, mapping=execution.to_json(), expire_time=cls.expire_time
        )

    @classmethod
    def _normalize_status(cls, status: Any) -> ExecutionStatus:
        """Intelligently normalize any status input to ExecutionStatus enum.

        Handles:
        - ExecutionStatus enum objects (pass-through)
        - Valid enum values: "PENDING", "EXECUTING", etc.
        - Legacy enum representations: "ExecutionStatus.PENDING"
        - Case variations and validates against known enum values

        Args:
            status: Any status input (enum, string, etc.)

        Returns:
            ExecutionStatus: Normalized enum object

        Raises:
            ValueError: If status cannot be normalized to valid ExecutionStatus
        """
        # Already an ExecutionStatus enum? Perfect!
        print(f"status ---------_normalize_status---------->>>: {status}")
        print(f"type(status) ---------_normalize_status---------->>>: {type(status)}")
        if isinstance(status, ExecutionStatus):
            return status

        # Convert to string for processing
        status_str = str(status).strip()

        # Try direct enum construction first (handles "PENDING", "EXECUTING", etc.)
        try:
            return ExecutionStatus(status_str)
        except ValueError:
            pass

        print(f"status_str ---------_normalize_status---------->>>: {status_str}")
        # Handle enum string representations by trying to extract the value
        # Works for: "ExecutionStatus.PENDING", "<ExecutionStatus.PENDING: 'PENDING'>", etc.
        for enum_member in ExecutionStatus:
            if enum_member.name in status_str:
                return enum_member

        # Last resort: try case-insensitive matching
        status_upper = status_str.upper()
        print(f"status_upper ---------_normalize_status---------->>>: {status_upper}")
        for enum_member in ExecutionStatus:
            if enum_member.value.upper() == status_upper:
                return enum_member

        # If we get here, it's truly invalid
        valid_values = [e.value for e in ExecutionStatus]
        raise ValueError(
            f"Cannot normalize status '{status}' (type: {type(status).__name__}) "
            f"to ExecutionStatus. Valid values: {valid_values}"
        )

    @classmethod
    def update_status(cls, workflow_id: str, execution_id: str, status: Any) -> None:
        """Update execution status with intelligent parsing."""
        status_enum = cls._normalize_status(status)
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
        """Delete execution."""
        cache_key = cls._get_execution_cache_key(
            workflow_id=workflow_id, execution_id=execution_id
        )
        CacheService.delete_a_key(cache_key)
