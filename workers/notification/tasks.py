"""Notification Worker Tasks

This module contains Celery tasks for processing all types of notifications.
It uses the provider registry pattern for platform-specific notification handling
while maintaining backward compatibility.
"""

import os
from typing import Any

from celery import shared_task
from notification.enums import PlatformType
from notification.providers.base_provider import (
    DeliveryError,
    NotificationError,
    ValidationError,
)
from notification.providers.registry import create_provider_from_config
from notification.providers.webhook_provider import WebhookProvider
from notification.utils import (
    log_notification_attempt,
    log_notification_failure,
    log_notification_success,
)
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import WorkerLogger

from unstract.core.notification_enums import NotificationType

logger = WorkerLogger.get_logger(__name__)

# Initialize worker configuration
config = WorkerConfig.from_env("NOTIFICATION")


def _get_webhook_provider_for_url(url: str):
    """Get webhook provider for backward compatibility.

    For backward compatibility with legacy webhook tasks that don't provide platform info.
    Always defaults to API provider since platform should come from notification configuration.

    Args:
        url: Webhook URL (used for logging only)

    Returns:
        API webhook provider instance
    """
    logger.debug(
        f"Legacy webhook task called without platform info for URL: {url[:50]}..."
    )

    # Always use API provider for backward compatibility
    # Platform detection should be done in backend and stored in database
    try:
        config = {
            "notification_type": NotificationType.WEBHOOK.value,
            "platform": PlatformType.API.value,
        }
        return create_provider_from_config(config)
    except Exception as e:
        logger.warning(
            f"Failed to create API provider: {e}. Using fallback WebhookProvider"
        )
        return WebhookProvider()


@shared_task(name="process_notification")
def process_notification(
    notification_type: str, priority: bool = False, **kwargs: Any
) -> dict[str, Any]:
    """Universal notification processor.

    This task routes notifications to the appropriate provider based on type.
    It provides a unified interface for all notification types while maintaining
    extensibility for future implementations.

    Args:
        notification_type: Type of notification (WEBHOOK, EMAIL, SMS, PUSH)
        **kwargs: Notification-specific parameters

    Returns:
        Dictionary containing the processing result

    Raises:
        NotificationError: If notification processing fails
    """
    destination = (
        kwargs.get("url") or kwargs.get("email") or kwargs.get("phone") or "unknown"
    )

    try:
        logger.info(f"Processing {notification_type} notification to {destination}")

        # Use the registry pattern with platform from config
        if notification_type == NotificationType.WEBHOOK.value:
            platform = kwargs.get("platform")
            if platform:
                config = {"notification_type": notification_type, "platform": platform}
                provider = create_provider_from_config(config)
                logger.debug(f"Selected provider: {provider.__class__.__name__}")
            else:
                # Backward compatibility: Default to API provider
                logger.warning("No platform specified, using API provider")
                provider = WebhookProvider()
        else:
            # For future notification types (EMAIL, SMS, etc.)
            raise NotificationError(
                f"Unsupported notification type: {notification_type}",
                provider="NotificationDispatcher",
                destination=destination,
            )

        log_notification_attempt(
            notification_type=notification_type,
            destination=destination,
            attempt=1,  # TODO: Track actual retry attempts
        )

        # Send notification
        result = provider.send(kwargs)

        if result.get("success"):
            log_notification_success(
                notification_type=notification_type,
                destination=destination,
                attempt=result.get("attempts", 1),
                response_info=result.get("details"),
            )
        else:
            log_notification_failure(
                notification_type=notification_type,
                destination=destination,
                error=Exception(result.get("message", "Unknown error")),
                attempt=result.get("attempts", 1),
                is_final=True,
            )

        return result

    except (ValidationError, DeliveryError) as e:
        logger.error(f"Notification error: {str(e)}")
        log_notification_failure(
            notification_type=notification_type,
            destination=destination,
            error=e,
            attempt=1,
            is_final=True,
        )
        return {
            "success": False,
            "message": str(e),
            "destination": destination,
            "error_type": e.__class__.__name__,
        }
    except Exception as e:
        logger.error(
            f"Unexpected error processing {notification_type} notification: {str(e)}"
        )
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}",
            "destination": destination,
            "error_type": e.__class__.__name__,
        }


@shared_task(bind=True, name="send_webhook_notification")
def send_webhook_notification(
    self,
    url: str,
    payload: Any,
    headers: Any = None,
    timeout: int = 10,
    max_retries: int | None = None,
    retry_delay: int = 10,
    platform: str | None = None,
) -> None:
    """Backward compatible webhook notification task.

    This task maintains 100% compatibility with the existing backend
    send_webhook_notification task. It delegates to the WebhookProvider
    but preserves the exact same interface and behavior.

    Args:
        url: The URL to which the webhook should be sent
        payload: The payload to be sent in the webhook request
        headers: Optional headers to include in the request
        timeout: The request timeout in seconds
        max_retries: The maximum number of retries allowed
        retry_delay: The delay between retries in seconds
        platform: Platform type from notification config (SLACK, API, etc.)

    Returns:
        None (matches original behavior)

    Raises:
        Exception: If webhook delivery fails (for Celery retry mechanism)
    """
    try:
        logger.debug(
            f"[{os.getpid()}] Processing webhook notification to {url} "
            f"(attempt {self.request.retries + 1})"
        )
        logger.debug(f"Task received platform parameter: {platform}")
        logger.debug(f"Task received payload type: {type(payload)}")
        logger.debug(f"Task received headers: {headers}")

        # Use platform-specific provider if provided, otherwise default to API for backward compatibility
        if platform:
            config = {
                "notification_type": NotificationType.WEBHOOK.value,
                "platform": platform,
            }
            webhook_provider = create_provider_from_config(config)
        else:
            webhook_provider = _get_webhook_provider_for_url(url)

        # Prepare notification data in the format expected by WebhookProvider
        notification_data = {
            "url": url,
            "payload": payload,
            "headers": headers,
            "timeout": timeout,
            "max_retries": max_retries,
            "retry_delay": retry_delay,
            "platform": platform,
        }

        # Send webhook notification
        result = webhook_provider.send(notification_data)

        # Handle result based on success/failure
        if result.get("success"):
            logger.info(
                f"Webhook delivered successfully to {url} "
                f"(status: {result.get('details', {}).get('status_code', 'unknown')})"
            )
            return None  # Success - matches original behavior
        else:
            # Failed delivery - raise exception for retry handling
            error_message = result.get("message", "Unknown webhook delivery error")
            raise Exception(error_message)

    except (ValidationError, DeliveryError) as e:
        # Handle provider-specific errors
        if max_retries is not None:
            if self.request.retries < max_retries:
                logger.warning(
                    f"Request to {url} failed. Retrying in {retry_delay} seconds. "
                    f"Attempt {self.request.retries + 1}/{max_retries}. Error: {e}"
                )
                # Use Celery's retry mechanism - identical to original behavior
                raise self.retry(exc=e, countdown=retry_delay)
            else:
                logger.error(
                    f"Failed to send webhook to {url} after {max_retries} attempts. "
                    f"Error: {e}"
                )
                return None  # Final failure - matches original behavior
        else:
            logger.error(f"Webhook request to {url} failed with error: {e}")
            return None  # No retries configured - matches original behavior

    except Exception as e:
        # Handle unexpected errors - preserve original retry logic
        if max_retries is not None:
            if self.request.retries < max_retries:
                logger.warning(
                    f"Request to {url} failed. Retrying in {retry_delay} seconds. "
                    f"Attempt {self.request.retries + 1}/{max_retries}. Error: {e}"
                )
                raise self.retry(exc=e, countdown=retry_delay)
            else:
                logger.error(
                    f"Failed to send webhook to {url} after {max_retries} attempts. "
                    f"Error: {e}"
                )
                return None
        else:
            logger.error(f"Webhook request to {url} failed with error: {e}")
            return None


@shared_task(name="send_batch_notifications")
def send_batch_notifications(
    notifications: list[dict[str, Any]],
    batch_id: str | None = None,
    delay_between: int = 0,
) -> dict[str, Any]:
    """Send multiple notifications in batch.

    This task processes multiple notifications with optional delays between them.
    It's designed for future enhancement of the notification system.

    Args:
        notifications: List of notification configurations
        batch_id: Optional batch identifier
        delay_between: Delay between notifications in seconds

    Returns:
        Dictionary with batch processing results
    """
    import uuid
    from datetime import datetime

    batch_id = batch_id or str(uuid.uuid4())

    logger.info(f"Processing batch {batch_id} with {len(notifications)} notifications")

    results = {
        "batch_id": batch_id,
        "total_notifications": len(notifications),
        "successful": [],
        "failed": [],
        "started_at": datetime.now().isoformat(),
    }

    for i, notification in enumerate(notifications):
        try:
            notification_type = notification.get("type", NotificationType.WEBHOOK.value)

            # Add delay between notifications if specified
            if delay_between > 0 and i > 0:
                import time

                time.sleep(delay_between)

            # Process notification
            result = process_notification(notification_type, **notification)

            if result.get("success"):
                results["successful"].append(
                    {
                        "index": i,
                        "destination": result.get("destination"),
                        "type": notification_type,
                    }
                )
            else:
                results["failed"].append(
                    {
                        "index": i,
                        "destination": result.get("destination"),
                        "type": notification_type,
                        "error": result.get("message"),
                    }
                )

        except Exception as e:
            logger.error(f"Batch notification {i} failed: {str(e)}")
            results["failed"].append(
                {
                    "index": i,
                    "destination": notification.get("url", "unknown"),
                    "type": notification.get("type", "unknown"),
                    "error": str(e),
                }
            )

    results["completed_at"] = datetime.now().isoformat()

    logger.info(
        f"Batch {batch_id} completed: {len(results['successful'])} successful, "
        f"{len(results['failed'])} failed"
    )

    return results


@shared_task(name="priority_notification")
def priority_notification(notification_type: str, **kwargs: Any) -> dict[str, Any]:
    """High-priority notification processor.

    This task is routed to the priority queue for urgent notifications
    that need immediate processing.

    Args:
        notification_type: Type of notification (WEBHOOK, EMAIL, SMS, PUSH)
        **kwargs: Notification-specific parameters

    Returns:
        Dictionary containing the processing result
    """
    logger.info(f"Processing priority {notification_type} notification")

    # Set priority flag and delegate to main processor
    return process_notification(notification_type, priority=True, **kwargs)


@shared_task(name="notification_health_check")
def notification_health_check() -> dict[str, Any]:
    """Health check task for notification worker."""
    try:
        queue_name = os.getenv("NOTIFICATION_QUEUE_NAME", "notifications")
        return {
            "worker": "notification",
            "status": "healthy",
            "queue": queue_name,
        }
    except Exception as e:
        return {"worker": "notification", "status": "unhealthy", "error": str(e)}
