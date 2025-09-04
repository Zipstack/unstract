"""Webhook API Client for Webhook Operations

This module provides specialized API client for webhook operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Webhook sending and delivery
- Webhook status tracking
- Webhook testing
- Webhook batch operations
- Webhook configuration management
"""

import logging

# Import shared AuthorizationType from core
import os
import sys
from typing import Any

from ..data.models import (
    APIResponse,
    BatchOperationRequest,
    BatchOperationResponse,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core.notification_enums import AuthorizationType

from ..enums import (
    BatchOperationType,
    TaskStatus,
)
from ..utils.retry_temp import CircuitBreakerOpenError, circuit_breaker
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class WebhookAPIClient(BaseAPIClient):
    """Specialized API client for webhook operations.

    This client handles all webhook-related operations including:
    - Sending webhook notifications
    - Checking webhook delivery status
    - Testing webhook configurations
    - Batch webhook operations
    - Webhook retry handling
    """

    def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        notification_id: str | None = None,
        authorization_type: str | AuthorizationType = AuthorizationType.NONE,
        authorization_key: str | None = None,
        authorization_header: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5,
        headers: dict[str, str] | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Send webhook notification to external endpoint.

        Args:
            url: Webhook endpoint URL
            payload: Webhook payload data
            notification_id: Optional notification ID for tracking
            authorization_type: Type of authorization (none, bearer, basic, custom)
            authorization_key: Authorization key/token
            authorization_header: Custom authorization header
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            headers: Additional HTTP headers
            organization_id: Optional organization ID override

        Returns:
            Webhook delivery response
        """
        # Convert authorization_type to string if it's an enum
        auth_type_str = (
            authorization_type.value
            if isinstance(authorization_type, AuthorizationType)
            else authorization_type
        )

        data = {
            "url": url,
            "payload": payload,
            "authorization_type": auth_type_str,
            "timeout": timeout,
            "max_retries": max_retries,
            "retry_delay": retry_delay,
        }

        # Add optional parameters
        if notification_id:
            data["notification_id"] = notification_id
        if authorization_key:
            data["authorization_key"] = authorization_key
        if authorization_header:
            data["authorization_header"] = authorization_header
        if headers:
            data["headers"] = headers

        logger.info(
            f"Sending webhook to {url} with payload size {len(str(payload))} characters"
        )
        logger.debug(f"Webhook authorization_type: {auth_type_str}")

        try:
            response = self.post(
                self._build_url("webhook", "send/"), data, organization_id=organization_id
            )

            logger.info(f"Successfully sent webhook to {url}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to send webhook to {url}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_webhook_status(
        self, task_id: str, organization_id: str | None = None
    ) -> dict[str, Any]:
        """Get webhook delivery status by task ID.

        Args:
            task_id: Webhook task ID
            organization_id: Optional organization ID override

        Returns:
            Webhook status information
        """
        logger.debug(f"Getting webhook status for task {task_id}")

        try:
            response = self.get(
                self._build_url("webhook", f"status/{task_id}/"),
                organization_id=organization_id,
            )

            status = response.get("status", "unknown")
            logger.debug(f"Webhook task {task_id} status: {status}")
            return response

        except Exception as e:
            logger.error(f"Failed to get webhook status for task {task_id}: {str(e)}")
            raise

    def test_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        authorization_type: str | AuthorizationType = AuthorizationType.NONE,
        authorization_key: str | None = None,
        authorization_header: str | None = None,
        timeout: int = 10,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Test webhook configuration and connectivity.

        Args:
            url: Webhook endpoint URL to test
            payload: Test payload data
            authorization_type: Type of authorization (none, bearer, basic, custom)
            authorization_key: Authorization key/token
            authorization_header: Custom authorization header
            timeout: Request timeout in seconds
            organization_id: Optional organization ID override

        Returns:
            Test result with success status and response details
        """
        # Convert authorization_type to string if it's an enum
        auth_type_str = (
            authorization_type.value
            if isinstance(authorization_type, AuthorizationType)
            else authorization_type
        )

        data = {
            "url": url,
            "payload": payload,
            "authorization_type": auth_type_str,
            "timeout": timeout,
        }

        # Add optional authorization
        if authorization_key:
            data["authorization_key"] = authorization_key
        if authorization_header:
            data["authorization_header"] = authorization_header

        logger.info(f"Testing webhook configuration for {url}")
        logger.debug(f"Test webhook authorization_type: {auth_type_str}")

        try:
            response = self.post(
                self._build_url("webhook", "test/"), data, organization_id=organization_id
            )

            success = response.get("success", False)
            logger.info(f"Webhook test for {url} {'succeeded' if success else 'failed'}")
            return APIResponse(
                success=success, data=response, status_code=response.get("status_code")
            )

        except Exception as e:
            logger.error(f"Failed to test webhook {url}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def batch_send_webhooks(
        self, webhooks: list[dict[str, Any]], organization_id: str | None = None
    ) -> BatchOperationResponse:
        """Send multiple webhooks in a single batch request.

        Args:
            webhooks: List of webhook configurations
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with individual results
        """
        import uuid

        batch_request = BatchOperationRequest(
            operation_type=BatchOperationType.CREATE,
            items=webhooks,
            organization_id=organization_id,
        )

        logger.info(f"Sending batch of {len(webhooks)} webhooks")

        try:
            response = self.post(
                self._build_url("webhook", "batch-send/"),
                batch_request.to_dict(),
                organization_id=organization_id,
            )

            successful = response.get("successful", 0)
            failed = response.get("failed", 0)
            logger.info(
                f"Batch webhook send completed: {successful} successful, {failed} failed"
            )

            return BatchOperationResponse(
                operation_id=response.get("operation_id", str(uuid.uuid4())),
                total_items=len(webhooks),
                successful_items=successful,
                failed_items=failed,
                status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
                results=response.get("results", []),
                errors=response.get("errors", []),
                execution_time=response.get("execution_time"),
            )

        except Exception as e:
            logger.error(f"Failed to send batch webhooks: {str(e)}")
            return BatchOperationResponse(
                operation_id=str(uuid.uuid4()),
                total_items=len(webhooks),
                successful_items=0,
                failed_items=len(webhooks),
                status=TaskStatus.FAILURE,
                results=[],
                errors=[{"error": str(e)}],
            )

    def get_webhook_delivery_history(
        self,
        notification_id: str | None = None,
        url: str | None = None,
        status: str | TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get webhook delivery history with filtering options.

        Args:
            notification_id: Filter by notification ID
            url: Filter by webhook URL
            status: Filter by delivery status
            limit: Maximum number of records to return
            offset: Number of records to skip
            organization_id: Optional organization ID override

        Returns:
            Paginated webhook delivery history
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        params = {"limit": limit, "offset": offset}

        if notification_id:
            params["notification_id"] = notification_id
        if url:
            params["url"] = url
        if status_str:
            params["status"] = status_str

        logger.debug(f"Getting webhook delivery history with filters: {params}")

        try:
            response = self.get(
                self._build_url("webhook", "history/"),
                params=params,
                organization_id=organization_id,
            )

            count = response.get("count", 0)
            logger.debug(f"Retrieved {count} webhook delivery records")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get webhook delivery history: {str(e)}")
            return APIResponse(success=False, error=str(e))

    @circuit_breaker(failure_threshold=3, recovery_timeout=60.0)
    def retry_failed_webhook(
        self,
        task_id: str,
        max_retries: int = 3,
        retry_delay: int = 5,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Retry a failed webhook delivery.

        Args:
            task_id: Failed webhook task ID
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            organization_id: Optional organization ID override

        Returns:
            Retry response
        """
        data = {
            "task_id": task_id,
            "max_retries": max_retries,
            "retry_delay": retry_delay,
        }

        logger.info(f"Retrying failed webhook task {task_id}")

        try:
            response = self.post(
                self._build_url("webhook", "retry/"),
                data,
                organization_id=organization_id,
            )

            logger.info(f"Successfully initiated retry for webhook task {task_id}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except CircuitBreakerOpenError:
            logger.warning(f"Webhook retry circuit breaker open for task {task_id}")
            return APIResponse(
                success=False,
                error="Circuit breaker open - webhook retry service unavailable",
            )
        except Exception as e:
            logger.error(f"Failed to retry webhook task {task_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def cancel_webhook(
        self, task_id: str, organization_id: str | None = None
    ) -> APIResponse:
        """Cancel a pending webhook delivery.

        Args:
            task_id: Webhook task ID to cancel
            organization_id: Optional organization ID override

        Returns:
            Cancellation response
        """
        data = {"task_id": task_id}

        logger.info(f"Cancelling webhook task {task_id}")

        try:
            response = self.post(
                self._build_url("webhook", "cancel/"),
                data,
                organization_id=organization_id,
            )

            logger.info(f"Successfully cancelled webhook task {task_id}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to cancel webhook task {task_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_webhook_metrics(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get webhook delivery metrics and statistics.

        Args:
            start_date: Start date for metrics (ISO format)
            end_date: End date for metrics (ISO format)
            organization_id: Optional organization ID override

        Returns:
            Webhook metrics including success rates, response times, etc.
        """
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        logger.debug(
            f"Getting webhook metrics for date range: {start_date} to {end_date}"
        )

        try:
            response = self.get(
                self._build_url("webhook", "metrics/"),
                params=params,
                organization_id=organization_id,
            )

            total_sent = response.get("total_sent", 0)
            success_rate = response.get("success_rate", 0.0)
            logger.debug(
                f"Webhook metrics: {total_sent} sent, {success_rate:.1%} success rate"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get webhook metrics: {str(e)}")
            return APIResponse(success=False, error=str(e))
