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

from ..manual_review_response import ManualReviewResponse

logger = logging.getLogger(__name__)


class ManualReviewNullClient:
    """Null object implementation for manual review functionality in OSS.

    This class provides safe, no-op implementations of all manual review methods,
    allowing the OSS version to function without manual review capabilities.
    All methods return appropriate default values that indicate manual review
    is not available or not required.
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
        """Get queue file numbers for manual review (returns empty list in OSS).

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
        return ManualReviewResponse.not_available_response(
            message="Manual review not available in OSS - no files selected for review"
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
        return ManualReviewResponse.not_available_response(
            message="Manual review not available in OSS - no rules configured"
        )

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
            return ManualReviewResponse.not_available_response(
                message=f"Manual review method '{name}' not available in OSS version"
            )

        return safe_default


# Alias for backward compatibility
ManualReviewAPIClient = ManualReviewNullClient

__all__ = [
    "ManualReviewNullClient",
    "ManualReviewAPIClient",  # Backward compatibility alias
]
