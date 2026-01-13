"""API Hub usage tracking utilities for workflow execution.

This module provides a clean interface for API Hub usage tracking in workflows.
Usage tracking functionality is loaded via get_plugin if available.
"""

import logging

from plugins import get_plugin

logger = logging.getLogger(__name__)


class APIHubUsageUtil:
    """Utility class for handling API Hub usage tracking in workflows."""

    @staticmethod
    def track_api_hub_usage(
        workflow_execution_id: str,
        workflow_file_execution_id: str,
        organization_id: str | None = None,
    ) -> bool:
        """Track API hub usage if the verticals_usage plugin is available.

        Args:
            workflow_execution_id: The workflow execution ID
            workflow_file_execution_id: The file execution ID
            organization_id: Optional organization ID

        Returns:
            bool: True if tracking succeeded, False otherwise.
        """
        verticals_usage_plugin = get_plugin("verticals_usage")
        if not verticals_usage_plugin:
            return False

        try:
            headers_cache = verticals_usage_plugin["headers_cache_class"]()
            usage_tracker = verticals_usage_plugin["service_class"]()

            api_hub_headers = headers_cache.get_headers(workflow_execution_id)

            if api_hub_headers:
                return usage_tracker.store_usage(
                    file_execution_id=workflow_file_execution_id,
                    api_hub_headers=api_hub_headers,
                    organization_id=organization_id,
                )
            return False

        except Exception as e:
            logger.error(
                f"Failed to track API hub usage for execution {workflow_execution_id}: {e}"
            )
            return False

    @staticmethod
    def extract_api_hub_headers(request_headers: dict) -> dict | None:
        """Extract API hub headers from request headers.

        Args:
            request_headers: Request headers dictionary

        Returns:
            Normalized API hub headers or None if not available.
        """
        verticals_usage_plugin = get_plugin("verticals_usage")
        if not verticals_usage_plugin:
            return None

        try:
            usage_tracker = verticals_usage_plugin["service_class"]()
            return usage_tracker.extract_api_hub_headers_from_request(request_headers)
        except Exception as e:
            logger.error(f"Error extracting API hub headers: {e}")
            return None

    @staticmethod
    def cache_api_hub_headers(
        execution_id: str,
        headers: dict,
        ttl_seconds: int = 7200,
    ) -> bool:
        """Cache API hub headers for later usage tracking.

        Args:
            execution_id: The execution ID to use as cache key
            headers: Headers to cache
            ttl_seconds: Time-to-live in seconds (default 2 hours)

        Returns:
            True if caching succeeded, False otherwise.
        """
        verticals_usage_plugin = get_plugin("verticals_usage")
        if not verticals_usage_plugin:
            return False

        try:
            headers_cache = verticals_usage_plugin["headers_cache_class"]()
            return headers_cache.store_headers(execution_id, headers)
        except Exception as e:
            logger.error(f"Error caching API hub headers: {e}")
            return False
