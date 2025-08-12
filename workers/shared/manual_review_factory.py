"""Manual Review Service Factory.

Simplified plugin-aware factory for manual review services.
Uses complete service implementations from plugins when available,
falls back to minimal OSS null service otherwise.
"""

from typing import Any, Protocol

from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class ManualReviewServiceProtocol(Protocol):
    """Protocol defining the interface for manual review services."""

    def get_manual_review_config(
        self, workflow_id: str, total_files: int = 0
    ) -> dict[str, Any]:
        """Get manual review configuration for a workflow."""
        ...

    def calculate_q_file_no_list(
        self, config: dict[str, Any], total_files: int
    ) -> list[int]:
        """Calculate file numbers for manual review queue."""
        ...

    def calculate_batch_decisions(
        self,
        batch: list[tuple[str, Any]],
        source_files: dict[str, Any],
        config: dict[str, Any],
    ) -> list[bool]:
        """Calculate manual review decisions for files in a batch."""
        ...

    def create_workflow_file_data_with_manual_review(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        pipeline_id: str | None,
        scheduled: bool,
        execution_mode: str | None,
        use_file_history: bool,
        total_files: int = 0,
    ) -> Any:
        """Create WorkerFileData with manual review configuration."""
        ...


class ManualReviewNullService:
    """Null implementation of manual review service for OSS compatibility."""

    def __init__(self, api_client: Any, organization_id: str):
        """Initialize null service."""
        self.api_client = api_client
        self.organization_id = organization_id
        logger.debug("Using ManualReviewNullService - manual review disabled in OSS")

    def get_manual_review_config(
        self, workflow_id: str, total_files: int = 0
    ) -> dict[str, Any]:
        """Return default config indicating no manual review."""
        return {
            "review_required": False,
            "review_percentage": 0,
            "rule_logic": None,
            "rule_json": None,
            "q_file_no_list": [],
            "file_decisions": [],
        }

    def calculate_q_file_no_list(
        self, config: dict[str, Any], total_files: int
    ) -> list[int]:
        """Return empty list for OSS."""
        return []

    def calculate_batch_decisions(
        self,
        batch: list[tuple[str, Any]],
        source_files: dict[str, Any],
        config: dict[str, Any],
    ) -> list[bool]:
        """Return all False for OSS."""
        return [False] * len(batch)

    def create_workflow_file_data_with_manual_review(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        pipeline_id: str | None,
        scheduled: bool,
        execution_mode: str | None,
        use_file_history: bool,
        total_files: int = 0,
    ) -> Any:
        """Create WorkerFileData without manual review for OSS."""
        from unstract.core.data_models import WorkerFileData

        return WorkerFileData(
            workflow_id=str(workflow_id),
            execution_id=str(execution_id),
            organization_id=str(organization_id),
            pipeline_id=str(pipeline_id) if pipeline_id else "",
            scheduled=scheduled,
            execution_mode=execution_mode or "SYNC",
            use_file_history=use_file_history,
            single_step=False,
            q_file_no_list=[],  # No files for manual review in OSS
            manual_review_config=self.get_manual_review_config(workflow_id, total_files),
        )


class ManualReviewServiceFactory:
    """Plugin-aware factory for manual review services."""

    @staticmethod
    def create_service(
        api_client: Any, organization_id: str
    ) -> ManualReviewServiceProtocol:
        """Create manual review service using plugins when available.

        Args:
            api_client: Internal API client
            organization_id: Organization ID

        Returns:
            Enhanced service if plugin available, null service otherwise
        """
        # Try to get enhanced service from plugin first
        enhanced_service = ManualReviewServiceFactory._try_plugin_service(
            api_client, organization_id
        )

        if enhanced_service:
            logger.debug("Using enhanced manual review service from plugin")
            return enhanced_service

        # Fall back to OSS null service
        logger.debug("Using OSS null manual review service")
        return ManualReviewNullService(api_client, organization_id)

    @staticmethod
    def _try_plugin_service(
        api_client: Any, organization_id: str
    ) -> ManualReviewServiceProtocol | None:
        """Try to create enhanced service from plugins."""
        try:
            from client_plugin_registry import get_client_plugin, has_client_plugin

            # Check for manual review service plugin
            if has_client_plugin("manual_review"):
                service_plugin = get_client_plugin("manual_review", api_client.config)
                if service_plugin:
                    # Set organization context on the service
                    service_plugin.set_organization_context(organization_id)
                    return service_plugin

            return None

        except Exception as e:
            logger.debug(f"Plugin service creation failed: {e}")
            return None


# Convenience function for easy usage
def get_manual_review_service(
    api_client: Any, organization_id: str
) -> ManualReviewServiceProtocol:
    """Get the appropriate manual review service using plugin registry.

    This function eliminates the need for try/except ImportError blocks.

    Args:
        api_client: Internal API client
        organization_id: Organization ID

    Returns:
        ManualReviewService if plugin available, ManualReviewNullService otherwise
    """
    return ManualReviewServiceFactory.create_service(api_client, organization_id)
