"""API Hub Usage Service Factory.

Plugin-aware factory for API Hub usage tracking services.
Uses complete service implementations from plugins when available,
falls back to minimal OSS null service otherwise.
"""

from typing import Protocol

from client_plugin_registry import get_client_plugin, has_client_plugin

from ..infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)

API_HUB_PLUGIN_NAME = "api_hub"


class APIHubServiceProtocol(Protocol):
    """Protocol defining the interface for API Hub usage services."""

    def track_api_hub_usage(
        self,
        workflow_execution_id: str,
        workflow_file_execution_id: str,
        organization_id: str | None = None,
    ) -> bool:
        """Track API hub usage for billing purposes."""
        ...


class NullAPIHubService:
    """Null implementation for OSS deployments.

    Provides safe no-op methods that don't raise errors when API Hub
    functionality is not available.
    """

    def track_api_hub_usage(
        self,
        workflow_execution_id: str,
        workflow_file_execution_id: str,
        organization_id: str | None = None,
    ) -> bool:
        """No-op implementation for OSS - always returns False."""
        logger.debug(
            f"API Hub plugin not available - skipping usage tracking for execution {workflow_execution_id}"
        )
        return False


def get_api_hub_service() -> APIHubServiceProtocol:
    """Get API Hub service instance.

    Returns enterprise plugin implementation if available,
    otherwise returns null service for graceful OSS fallback.

    Returns:
        APIHubServiceProtocol: Service instance (plugin or null implementation)
    """
    logger.info("Checking for API Hub plugin availability")
    if has_client_plugin(API_HUB_PLUGIN_NAME):
        logger.info("API Hub plugin available - using enterprise implementation")
        try:
            # Get plugin instance from registry
            plugin_instance = get_client_plugin(API_HUB_PLUGIN_NAME)
            if plugin_instance:
                # Plugin provides direct access to APIHubUsageUtil methods
                return plugin_instance
            else:
                logger.warning(
                    "API Hub plugin instance creation failed - using null service"
                )
                return NullAPIHubService()
        except Exception as e:
            logger.warning(f"Error loading API Hub plugin - using null service: {e}")
            return NullAPIHubService()
    else:
        logger.error("API Hub plugin not available - using null service for OSS")
        return NullAPIHubService()


def has_api_hub_plugin() -> bool:
    """Check if API Hub plugin is available.

    Returns:
        bool: True if plugin is available, False for OSS deployments
    """
    return has_client_plugin(API_HUB_PLUGIN_NAME)


# Legacy compatibility - create a default service instance
# that can be imported directly for backward compatibility
_default_service = None


def get_default_api_hub_service() -> APIHubServiceProtocol:
    """Get default API Hub service instance (cached).

    This provides a cached instance for performance when the same
    service is used multiple times.

    Returns:
        APIHubServiceProtocol: Cached service instance
    """
    global _default_service
    if _default_service is None:
        _default_service = get_api_hub_service()
    return _default_service


# Create compatibility class that mimics the original APIHubUsageUtil
class APIHubUsageUtil:
    """Compatibility wrapper for the original APIHubUsageUtil class.

    This class provides the same interface as the original backend APIHubUsageUtil
    but uses the plugin system internally for proper separation of concerns.
    """

    _service = None

    @classmethod
    def _get_service(cls) -> APIHubServiceProtocol:
        """Get service instance (cached)."""
        if cls._service is None:
            cls._service = get_api_hub_service()
        return cls._service

    @staticmethod
    def track_api_hub_usage(
        workflow_execution_id: str,
        workflow_file_execution_id: str,
        organization_id: str | None = None,
    ) -> bool:
        """Track API hub usage for billing purposes.

        Args:
            workflow_execution_id: The workflow execution ID
            workflow_file_execution_id: The file execution ID
            organization_id: Optional organization ID

        Returns:
            bool: True if usage was tracked successfully, False otherwise.
        """
        service = APIHubUsageUtil._get_service()
        return service.track_api_hub_usage(
            workflow_execution_id=workflow_execution_id,
            workflow_file_execution_id=workflow_file_execution_id,
            organization_id=organization_id,
        )
