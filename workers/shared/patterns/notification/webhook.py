"""Worker-Native Webhook Service

This module provides worker-native webhook operations without backend dependency.
Handles all external HTTP requests within workers to eliminate backend load.
"""

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

# Import worker infrastructure
from ...infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkerWebhookService:
    """Handle webhook operations within workers without backend dependency"""

    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_MAX_ATTEMPTS = 3
    DEFAULT_BACKOFF_FACTOR = 2.0

    @staticmethod
    def validate_webhook_url(webhook_url: str) -> dict[str, Any]:
        """Validate webhook URL for security and accessibility.

        Args:
            webhook_url: URL to validate

        Returns:
            Dictionary with validation results
        """
        validation = {"is_valid": True, "errors": []}

        try:
            # Parse URL
            parsed = urlparse(webhook_url)

            # Check scheme
            if parsed.scheme not in ["http", "https"]:
                validation["is_valid"] = False
                validation["errors"].append(
                    f"Invalid scheme: {parsed.scheme}. Only http/https allowed."
                )

            # Check hostname
            if not parsed.hostname:
                validation["is_valid"] = False
                validation["errors"].append("Missing hostname in URL")

            # Security checks - block localhost and internal IPs
            if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
                validation["is_valid"] = False
                validation["errors"].append("Localhost URLs not allowed for security")

            # Block private IP ranges (basic check)
            if parsed.hostname.startswith(("10.", "172.", "192.168.")):
                validation["is_valid"] = False
                validation["errors"].append("Private IP addresses not allowed")

        except Exception as e:
            validation["is_valid"] = False
            validation["errors"].append(f"URL parsing failed: {str(e)}")

        return validation

    @staticmethod
    async def send_webhook_async(
        webhook_url: str,
        payload: dict[str, Any],
        organization_id: str,
        retry_config: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send webhook with worker-native retry logic (async version).

        Args:
            webhook_url: Webhook URL to send to
            payload: JSON payload to send
            organization_id: Organization ID for context
            retry_config: Retry configuration (optional)
            headers: Additional headers (optional)

        Returns:
            Dictionary with send results
        """
        # Validate webhook URL first
        url_validation = WorkerWebhookService.validate_webhook_url(webhook_url)
        if not url_validation["is_valid"]:
            return {
                "status": "failed",
                "error": f"Invalid webhook URL: {url_validation['errors']}",
                "attempts": 0,
            }

        # Configure retry parameters
        retry_config = retry_config or {}
        max_attempts = retry_config.get(
            "max_attempts", WorkerWebhookService.DEFAULT_MAX_ATTEMPTS
        )
        backoff_factor = retry_config.get(
            "backoff_factor", WorkerWebhookService.DEFAULT_BACKOFF_FACTOR
        )
        timeout = retry_config.get("timeout", WorkerWebhookService.DEFAULT_TIMEOUT)

        # Prepare headers
        request_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Unstract-Worker/1.0",
            "X-Organization-ID": organization_id,
            "X-Timestamp": str(int(time.time())),
        }

        if headers:
            request_headers.update(headers)

        logger.info(f"Sending webhook to {webhook_url} for org {organization_id}")

        # Attempt webhook delivery with retries
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for attempt in range(max_attempts):
                attempt_start = time.time()

                try:
                    logger.debug(
                        f"Webhook attempt {attempt + 1}/{max_attempts} to {webhook_url}"
                    )

                    response = await client.post(
                        webhook_url, json=payload, headers=request_headers
                    )

                    response_time = int((time.time() - attempt_start) * 1000)

                    # Check if request was successful
                    response.raise_for_status()

                    # Try to parse response JSON
                    try:
                        response_data = response.json() if response.content else None
                    except json.JSONDecodeError:
                        response_data = response.text if response.content else None

                    result = {
                        "status": "success",
                        "response_status": response.status_code,
                        "response_data": response_data,
                        "response_headers": dict(response.headers),
                        "response_time_ms": response_time,
                        "attempt": attempt + 1,
                        "url": webhook_url,
                    }

                    logger.info(
                        f"Webhook delivered successfully to {webhook_url} (attempt {attempt + 1}, {response_time}ms)"
                    )
                    return result

                except httpx.HTTPStatusError as e:
                    error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
                    logger.warning(
                        f"Webhook attempt {attempt + 1} HTTP error: {error_msg}"
                    )

                    # Don't retry on client errors (4xx)
                    if 400 <= e.response.status_code < 500:
                        return {
                            "status": "failed",
                            "error": error_msg,
                            "response_status": e.response.status_code,
                            "attempts": attempt + 1,
                            "url": webhook_url,
                        }

                except (httpx.RequestError, httpx.TimeoutException) as e:
                    error_msg = f"Request error: {str(e)}"
                    logger.warning(f"Webhook attempt {attempt + 1} failed: {error_msg}")

                except Exception as e:
                    error_msg = f"Unexpected error: {str(e)}"
                    logger.error(
                        f"Webhook attempt {attempt + 1} unexpected error: {error_msg}"
                    )

                # If this was the last attempt, return failure
                if attempt == max_attempts - 1:
                    return {
                        "status": "failed",
                        "error": error_msg,
                        "attempts": max_attempts,
                        "url": webhook_url,
                    }

                # Wait before retry with exponential backoff
                wait_time = backoff_factor**attempt
                logger.debug(f"Waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)

    @staticmethod
    def send_webhook(
        webhook_url: str,
        payload: dict[str, Any],
        organization_id: str,
        retry_config: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send webhook with worker-native retry logic (synchronous wrapper).

        Args:
            webhook_url: Webhook URL to send to
            payload: JSON payload to send
            organization_id: Organization ID for context
            retry_config: Retry configuration (optional)
            headers: Additional headers (optional)

        Returns:
            Dictionary with send results
        """
        try:
            # Run async webhook in event loop
            return asyncio.run(
                WorkerWebhookService.send_webhook_async(
                    webhook_url=webhook_url,
                    payload=payload,
                    organization_id=organization_id,
                    retry_config=retry_config,
                    headers=headers,
                )
            )
        except Exception as e:
            logger.error(f"Failed to send webhook to {webhook_url}: {str(e)}")
            return {
                "status": "failed",
                "error": f"Webhook execution failed: {str(e)}",
                "attempts": 0,
                "url": webhook_url,
            }

    @staticmethod
    async def send_webhooks_batch(
        webhooks: list[dict[str, Any]], organization_id: str, max_concurrent: int = 5
    ) -> list[dict[str, Any]]:
        """Send multiple webhooks concurrently.

        Args:
            webhooks: List of webhook configurations
            organization_id: Organization ID for context
            max_concurrent: Maximum concurrent webhook sends

        Returns:
            List of webhook send results
        """
        logger.info(
            f"Sending {len(webhooks)} webhooks concurrently (max {max_concurrent})"
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def send_single_webhook(webhook_config: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await WorkerWebhookService.send_webhook_async(
                    webhook_url=webhook_config["url"],
                    payload=webhook_config["payload"],
                    organization_id=organization_id,
                    retry_config=webhook_config.get("retry_config"),
                    headers=webhook_config.get("headers"),
                )

        # Execute all webhooks concurrently
        tasks = [send_single_webhook(webhook) for webhook in webhooks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    {
                        "status": "failed",
                        "error": f"Exception during webhook send: {str(result)}",
                        "url": webhooks[i].get("url", "unknown"),
                        "attempts": 0,
                    }
                )
            else:
                processed_results.append(result)

        success_count = sum(1 for r in processed_results if r.get("status") == "success")
        logger.info(f"Batch webhook results: {success_count}/{len(webhooks)} successful")

        return processed_results

    @staticmethod
    def create_webhook_payload(
        event_type: str,
        execution_id: str,
        workflow_id: str,
        organization_id: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create standardized webhook payload.

        Args:
            event_type: Type of event (e.g., 'workflow.completed')
            execution_id: Execution ID
            workflow_id: Workflow ID
            organization_id: Organization ID
            data: Event-specific data
            metadata: Additional metadata (optional)

        Returns:
            Standardized webhook payload
        """
        payload = {
            "event_type": event_type,
            "timestamp": int(time.time()),
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "organization_id": organization_id,
            "data": data,
            "metadata": metadata or {},
            "version": "1.0",
        }

        logger.debug(f"Created webhook payload for event {event_type}")
        return payload

    @staticmethod
    def test_webhook_connectivity(
        webhook_url: str, organization_id: str, timeout: int = 10
    ) -> dict[str, Any]:
        """Test webhook connectivity without sending actual data.

        Args:
            webhook_url: Webhook URL to test
            organization_id: Organization ID for context
            timeout: Timeout in seconds

        Returns:
            Dictionary with connectivity test results
        """
        logger.info(f"Testing webhook connectivity to {webhook_url}")

        # Validate URL first
        url_validation = WorkerWebhookService.validate_webhook_url(webhook_url)
        if not url_validation["is_valid"]:
            return {
                "is_reachable": False,
                "errors": url_validation["errors"],
                "response_time_ms": None,
            }

        test_payload = {
            "event_type": "test.connectivity",
            "timestamp": int(time.time()),
            "organization_id": organization_id,
            "test": True,
        }

        try:
            result = asyncio.run(
                WorkerWebhookService.send_webhook_async(
                    webhook_url=webhook_url,
                    payload=test_payload,
                    organization_id=organization_id,
                    retry_config={"max_attempts": 1, "timeout": timeout},
                )
            )

            return {
                "is_reachable": result["status"] == "success",
                "response_status": result.get("response_status"),
                "response_time_ms": result.get("response_time_ms"),
                "errors": [] if result["status"] == "success" else [result.get("error")],
            }

        except Exception as e:
            return {
                "is_reachable": False,
                "errors": [f"Connectivity test failed: {str(e)}"],
                "response_time_ms": None,
            }


class WorkerWebhookEventPublisher:
    """Publish workflow events via webhooks using worker-native operations"""

    def __init__(self, organization_id: str):
        """Initialize webhook event publisher.

        Args:
            organization_id: Organization ID for context
        """
        self.organization_id = organization_id
        self.webhook_service = WorkerWebhookService()

    def publish_workflow_started(
        self,
        execution_id: str,
        workflow_id: str,
        webhook_urls: list[str],
        total_files: int = 0,
    ) -> list[dict[str, Any]]:
        """Publish workflow started event.

        Args:
            execution_id: Execution ID
            workflow_id: Workflow ID
            webhook_urls: List of webhook URLs to notify
            total_files: Total number of files to process

        Returns:
            List of webhook send results
        """
        payload = self.webhook_service.create_webhook_payload(
            event_type="workflow.started",
            execution_id=execution_id,
            workflow_id=workflow_id,
            organization_id=self.organization_id,
            data={"total_files": total_files, "status": "EXECUTING"},
        )

        return self._send_to_multiple_webhooks(webhook_urls, payload)

    def publish_workflow_completed(
        self,
        execution_id: str,
        workflow_id: str,
        webhook_urls: list[str],
        execution_results: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Publish workflow completed event.

        Args:
            execution_id: Execution ID
            workflow_id: Workflow ID
            webhook_urls: List of webhook URLs to notify
            execution_results: Workflow execution results

        Returns:
            List of webhook send results
        """
        payload = self.webhook_service.create_webhook_payload(
            event_type="workflow.completed",
            execution_id=execution_id,
            workflow_id=workflow_id,
            organization_id=self.organization_id,
            data={"status": "COMPLETED", "results": execution_results},
        )

        return self._send_to_multiple_webhooks(webhook_urls, payload)

    def publish_workflow_failed(
        self,
        execution_id: str,
        workflow_id: str,
        webhook_urls: list[str],
        error_details: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Publish workflow failed event.

        Args:
            execution_id: Execution ID
            workflow_id: Workflow ID
            webhook_urls: List of webhook URLs to notify
            error_details: Error details

        Returns:
            List of webhook send results
        """
        payload = self.webhook_service.create_webhook_payload(
            event_type="workflow.failed",
            execution_id=execution_id,
            workflow_id=workflow_id,
            organization_id=self.organization_id,
            data={"status": "ERROR", "error": error_details},
        )

        return self._send_to_multiple_webhooks(webhook_urls, payload)

    def _send_to_multiple_webhooks(
        self, webhook_urls: list[str], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Send payload to multiple webhook URLs.

        Args:
            webhook_urls: List of webhook URLs
            payload: Payload to send

        Returns:
            List of send results
        """
        if not webhook_urls:
            return []

        webhooks = [{"url": url, "payload": payload} for url in webhook_urls]

        try:
            return asyncio.run(
                self.webhook_service.send_webhooks_batch(
                    webhooks=webhooks, organization_id=self.organization_id
                )
            )
        except Exception as e:
            logger.error(f"Failed to send batch webhooks: {str(e)}")
            return [
                {
                    "status": "failed",
                    "error": f"Batch send failed: {str(e)}",
                    "url": url,
                    "attempts": 0,
                }
                for url in webhook_urls
            ]
