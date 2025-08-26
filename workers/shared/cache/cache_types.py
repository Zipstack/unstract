"""Cache Type Constants and Enums

This module defines constants for cache types to avoid magic strings
and provide a single point of configuration for cache operations.
"""

from enum import Enum


class CacheType(str, Enum):
    """Enumeration of cache types for different API operations.

    Using str enum so values can be used directly as strings while
    providing IDE autocomplete and validation benefits.
    """

    # Core workflow operations
    WORKFLOW = "workflow"
    WORKFLOW_ENDPOINTS = "workflow_endpoints"
    WORKFLOW_DEFINITION = "workflow_definition"  # Alias for workflow

    # API deployment operations
    API_DEPLOYMENT = "api_deployment"

    # Tool and component operations
    TOOL_INSTANCES = "tool_instances"

    # Pipeline operations
    PIPELINE = "pipeline"
    PIPELINE_DATA = "pipeline_data"

    # Configuration and system operations
    CONFIGURATION = "configuration"
    PLATFORM_SETTINGS = "platform_settings"

    # File and execution operations
    FILE_BATCH = "file_batch"
    EXECUTION_DATA = "execution_data"

    # Custom/generic operations
    CUSTOM = "custom"


class CacheConfig:
    """Configuration for cache operations including TTL values."""

    # Default TTL values for different cache types (in seconds)
    DEFAULT_TTLS: dict[CacheType, int] = {
        CacheType.WORKFLOW: 60,  # Workflow definitions change infrequently
        CacheType.WORKFLOW_ENDPOINTS: 60,  # Endpoints change infrequently
        CacheType.WORKFLOW_DEFINITION: 60,  # Alias for workflow
        CacheType.API_DEPLOYMENT: 45,  # API deployments may change more often
        CacheType.TOOL_INSTANCES: 30,  # Tool instances may change during development
        CacheType.PIPELINE: 60,  # Pipeline configurations change infrequently
        CacheType.PIPELINE_DATA: 45,  # Pipeline data may update more frequently
        CacheType.CONFIGURATION: 120,  # System configuration changes rarely
        CacheType.PLATFORM_SETTINGS: 300,  # Platform settings change very rarely
        CacheType.FILE_BATCH: 15,  # File batches are more dynamic
        CacheType.EXECUTION_DATA: 30,  # Execution data has moderate lifetime
        CacheType.CUSTOM: 30,  # Default for custom operations
    }

    @classmethod
    def get_ttl(cls, cache_type: CacheType) -> int:
        """Get TTL for a cache type.

        Args:
            cache_type: The cache type enum value

        Returns:
            TTL in seconds
        """
        return cls.DEFAULT_TTLS.get(cache_type, cls.DEFAULT_TTLS[CacheType.CUSTOM])

    @classmethod
    def set_ttl(cls, cache_type: CacheType, ttl: int):
        """Update TTL for a cache type.

        Args:
            cache_type: The cache type enum value
            ttl: TTL in seconds
        """
        cls.DEFAULT_TTLS[cache_type] = ttl

    @classmethod
    def get_all_types(cls) -> list[CacheType]:
        """Get all available cache types.

        Returns:
            List of all cache type enum values
        """
        return list(CacheType)


# Convenience constants for commonly used cache types
# These can be imported directly for cleaner code
WORKFLOW_CACHE = CacheType.WORKFLOW
API_DEPLOYMENT_CACHE = CacheType.API_DEPLOYMENT
TOOL_INSTANCES_CACHE = CacheType.TOOL_INSTANCES
WORKFLOW_ENDPOINTS_CACHE = CacheType.WORKFLOW_ENDPOINTS
PIPELINE_CACHE = CacheType.PIPELINE
CONFIGURATION_CACHE = CacheType.CONFIGURATION


# Validation helper
def validate_cache_type(cache_type: str) -> CacheType:
    """Validate and convert string to CacheType enum.

    Args:
        cache_type: String representation of cache type

    Returns:
        CacheType enum value

    Raises:
        ValueError: If cache_type is not valid
    """
    try:
        return CacheType(cache_type)
    except ValueError:
        valid_types = [t.value for t in CacheType]
        raise ValueError(f"Invalid cache type '{cache_type}'. Valid types: {valid_types}")


# Backward compatibility mapping for any existing string usage
LEGACY_MAPPING = {
    "workflow": CacheType.WORKFLOW,
    "api_deployment": CacheType.API_DEPLOYMENT,
    "tool_instances": CacheType.TOOL_INSTANCES,
    "workflow_endpoints": CacheType.WORKFLOW_ENDPOINTS,
    "pipeline": CacheType.PIPELINE,
    "configuration": CacheType.CONFIGURATION,
    "custom": CacheType.CUSTOM,
}
