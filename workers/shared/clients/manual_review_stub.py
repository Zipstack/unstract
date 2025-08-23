"""Manual Review Null Client - OSS Compatibility

This module provides a null object implementation of the manual review client
for the OSS version of Unstract. It provides safe defaults and no-op implementations
for all manual review functionality, allowing the OSS version to work seamlessly
without any manual review code.

The null object pattern eliminates the need for conditional checks throughout
the codebase while ensuring graceful degradation when manual review functionality
is not available.
"""

import logging
from typing import Any

from ..enums import FileDestinationType
from ..manual_review_response import ManualReviewResponse

logger = logging.getLogger(__name__)

# Stub uses simple dicts - no need for complex dataclasses when manual review is disabled


class ManualReviewNullClient:
    """Null object implementation for manual review functionality in OSS.

    This class provides safe, no-op implementations of all manual review
    methods, allowing the OSS version to function without manual review
    capabilities. All methods return appropriate default values that
    indicate manual review is not available or not required.
    """

    def __init__(self, config: Any = None):
        """Initialize the null client.

        Args:
            config: Configuration object (ignored in null implementation)
        """
        self.config = config
        logger.debug("Initialized ManualReviewNullClient - manual review disabled in OSS")

    def set_organization_context(self, organization_id: str) -> None:
        """Set organization context (no-op in null implementation).

        Args:
            organization_id: Organization ID
        """
        logger.debug(
            f"ManualReviewNullClient: set_organization_context called with {organization_id} - no-op"
        )

    def get_q_no_list(
        self, workflow_id: str, total_files: int, organization_id: str | None = None
    ) -> ManualReviewResponse:
        """Get queue file numbers for manual review (returns empty list in
        OSS).

        Args:
            workflow_id: Workflow ID
            total_files: Total number of files
            organization_id: Organization ID

        Returns:
            ManualReviewResponse with empty q_file_no_list indicating no files for manual review
        """
        logger.debug(
            f"ManualReviewNullClient: get_q_no_list called for workflow {workflow_id} - returning empty list"
        )
        return ManualReviewResponse.success_response(
            data={"q_file_no_list": []},
            message="Manual review not available in OSS - no files selected for review",
        )

    def get_db_rules_data(
        self, workflow_id: str, organization_id: str | None = None
    ) -> ManualReviewResponse:
        """Get database rules for manual review (returns no rules in OSS).

        Args:
            workflow_id: Workflow ID
            organization_id: Organization ID

        Returns:
            ManualReviewResponse indicating no manual review rules are configured
        """
        logger.debug(
            f"ManualReviewNullClient: get_db_rules_data called for workflow {workflow_id} - returning no rules"
        )
        return ManualReviewResponse.success_response(
            data={"rules": [], "percentage": 0, "review_required": False},
            message="Manual review not available in OSS - no rules configured",
        )

    def enqueue_manual_review(self, *args, **kwargs) -> dict[str, Any]:
        """Enqueue item for manual review (no-op in OSS).

        Returns:
            Dictionary indicating manual review is not available
        """
        logger.debug(
            "ManualReviewNullClient: enqueue_manual_review called - not available in OSS"
        )
        return {
            "success": False,
            "message": "Manual review not available in OSS version",
            "queue_name": None,
        }

    def route_to_manual_review(
        self,
        file_execution_id: str,
        file_data: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Route file to manual review (no-op in OSS).

        In OSS, files marked for manual review are processed normally
        since there's no manual review backend infrastructure.

        Args:
            file_execution_id: Workflow file execution ID
            file_data: File hash data dictionary
            workflow_id: Workflow UUID
            execution_id: Execution UUID
            organization_id: Organization context

        Returns:
            Dictionary indicating manual review routing skipped
        """
        logger.debug(
            f"ManualReviewNullClient: route_to_manual_review called for file {file_data.get('file_name', 'unknown')} - skipping in OSS"
        )
        return {
            "success": True,  # Return success to avoid blocking workflow
            "message": "Manual review not available in OSS - file will be processed normally",
            "queue_name": f"review_queue_{organization_id}_{workflow_id}",
            "skipped": True,
        }

    def route_with_results(
        self,
        file_execution_id: str,
        file_data: dict[str, Any],
        workflow_result: dict[str, Any],
        workflow_id: str,
        execution_id: str,
        organization_id: str | None = None,
        file_name: str = "unknown",
    ) -> dict[str, Any]:
        """Route file to manual review with results (no-op in OSS).

        In OSS, files marked for manual review are processed normally
        since manual review functionality is not available.

        Args:
            file_execution_id: Workflow file execution ID
            file_data: File hash data dictionary
            workflow_result: Results from tool execution
            workflow_id: Workflow UUID
            execution_id: Execution UUID
            organization_id: Organization context
            file_name: File name for logging

        Returns:
            Dictionary indicating manual review routing skipped, includes results
        """
        logger.debug(
            f"ManualReviewNullClient: route_with_results called for file {file_name} - skipping in OSS"
        )

        # Extract tool results from workflow_result for consistency
        tool_result = None
        if workflow_result and "result" in workflow_result:
            tool_result = workflow_result["result"]
        elif workflow_result and "output" in workflow_result:
            tool_result = workflow_result["output"]
        else:
            tool_result = workflow_result

        # Simple dict return for OSS stub - no dataclass complexity needed
        return {
            "success": True,  # Return success to avoid blocking workflow
            "message": "Manual review not available in OSS - file processed normally with results",
            "file": file_name,
            "file_execution_id": file_execution_id,
            "error": None,
            "result": tool_result,
            "metadata": {
                "routed_to_manual_review": False,
                "has_tool_results": tool_result is not None,
                "processed_before_review": True,
                "oss_mode": True,
            },
            "manual_review": False,
            "skipped": True,
        }

    def dequeue_manual_review(self, *args, **kwargs) -> dict[str, Any]:
        """Dequeue item from manual review (no-op in OSS).

        Returns:
            Dictionary indicating no items available for review
        """
        logger.debug(
            "ManualReviewNullClient: dequeue_manual_review called - not available in OSS"
        )
        return {
            "success": False,
            "message": "Manual review not available in OSS version",
            "item": None,
        }

    def validate_manual_review_db_rule(self, *args, **kwargs) -> dict[str, Any]:
        """Validate manual review database rule (no-op in OSS).

        Returns:
            Dictionary indicating validation is not available
        """
        logger.debug(
            "ManualReviewNullClient: validate_manual_review_db_rule called - not available in OSS"
        )
        return {
            "valid": False,
            "message": "Manual review validation not available in OSS version",
        }

    def get_hitl_settings(
        self, workflow_id: str, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get HITL settings for workflow (returns disabled in OSS).

        Args:
            workflow_id: Workflow ID
            organization_id: Organization ID

        Returns:
            Dictionary indicating HITL is disabled
        """
        logger.debug(
            f"ManualReviewNullClient: get_hitl_settings called for workflow {workflow_id} - returning disabled"
        )
        return {
            "enabled": False,
            "percentage": 0,
            "auto_approval": False,
            "message": "HITL settings not available in OSS version",
        }

    def get_manual_review_workflows(
        self,
        connection_type: str = FileDestinationType.MANUALREVIEW.value,
        organization_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get workflows configured for manual review (returns empty list in
        OSS).

        Args:
            connection_type: Connection type filter
            organization_id: Organization ID

        Returns:
            Empty list indicating no workflows have manual review
        """
        logger.debug(
            "ManualReviewNullClient: get_manual_review_workflows called - returning empty list"
        )
        return []

    def get_queue_statistics(self, *args, **kwargs) -> dict[str, Any]:
        """Get manual review queue statistics (returns empty stats in OSS).

        Returns:
            Dictionary with empty queue statistics
        """
        logger.debug(
            "ManualReviewNullClient: get_queue_statistics called - returning empty stats"
        )
        return {
            "total_queues": 0,
            "total_items": 0,
            "pending_review": 0,
            "pending_approval": 0,
            "message": "Queue statistics not available in OSS version",
        }

    def close(self) -> None:
        """Close the client (no-op in null implementation)."""
        logger.debug("ManualReviewNullClient: close called - no-op")
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __getattr__(self, name: str) -> Any:
        """Handle any other method calls with safe defaults.

        Args:
            name: Method name that was called

        Returns:
            A function that returns safe defaults
        """
        logger.debug(
            f"ManualReviewNullClient: unknown method '{name}' called - returning safe default"
        )

        def safe_default(*args, **kwargs):
            return {
                "success": False,
                "message": f"Manual review method '{name}' not available in OSS version",
                "data": None,
            }

        return safe_default


# Alias for backward compatibility
ManualReviewAPIClient = ManualReviewNullClient

__all__ = [
    "ManualReviewNullClient",
    "ManualReviewAPIClient",  # Backward compatibility alias
]
