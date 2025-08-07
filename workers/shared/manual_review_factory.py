"""Manual Review Service Factory - OSS Compatible Version

This factory provides manual review services using the plugin registry pattern.
In the OSS version, it automatically falls back to null services that provide
safe defaults for all manual review operations.
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
    """Factory for creating manual review services using plugin registry."""

    @staticmethod
    def create_service(
        api_client: Any, organization_id: str
    ) -> ManualReviewServiceProtocol:
        """Create appropriate manual review service based on plugin availability.

        In OSS, this always returns ManualReviewNullService since enterprise
        manual review plugins are not available.

        Args:
            api_client: Internal API client
            organization_id: Organization ID

        Returns:
            ManualReviewNullService for OSS compatibility
        """
        logger.debug(
            "OSS version - using ManualReviewNullService (manual review disabled)"
        )
        return ManualReviewNullService(api_client, organization_id)


# Convenience function for easy usage
def get_manual_review_service(
    api_client: Any, organization_id: str
) -> ManualReviewServiceProtocol:
    """Get the appropriate manual review service.

    In OSS, this always returns the null service that provides safe defaults.

    Args:
        api_client: Internal API client
        organization_id: Organization ID

    Returns:
        ManualReviewNullService for OSS compatibility
    """
    return ManualReviewServiceFactory.create_service(api_client, organization_id)
