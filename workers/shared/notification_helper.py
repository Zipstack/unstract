"""Lightweight notification helper for callback worker.

Handles notification triggering integrated with status updates.
No Django dependencies, works in pure worker environment.
"""

import logging

from celery import current_app

# Import shared data models from @unstract/core
try:
    from unstract.core.data_models import (
        ExecutionStatus,
        NotificationPayload,
        NotificationSource,
        WorkflowType,
    )
except ImportError:
    # Fallback for testing environments
    logging.warning("Could not import shared data models from unstract.core")

    class ExecutionStatus:
        COMPLETED = "COMPLETED"
        ERROR = "ERROR"
        STOPPED = "STOPPED"

    class NotificationStatus:
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"

    class WorkflowType:
        API = "API"
        ETL = "ETL"

    class NotificationSource:
        CALLBACK_WORKER = "callback-worker"


logger = logging.getLogger(__name__)


def get_webhook_headers(
    auth_type: str, auth_key: str | None, auth_header: str | None
) -> dict[str, str]:
    """Generate webhook headers based on authorization configuration."""
    headers = {"Content-Type": "application/json"}

    try:
        if auth_type and auth_key:
            auth_type_upper = auth_type.upper()

            if auth_type_upper == "BEARER":
                headers["Authorization"] = f"Bearer {auth_key}"
            elif auth_type_upper == "API_KEY":
                headers["Authorization"] = auth_key
            elif auth_type_upper == "CUSTOM_HEADER" and auth_header:
                headers[auth_header] = auth_key
            # NONE type just uses Content-Type header
    except Exception as e:
        logger.warning(f"Error generating webhook headers: {e}")
        # Use default headers if auth config is invalid

    return headers


def send_notification_to_worker(
    url: str,
    payload: NotificationPayload,
    auth_type: str,
    auth_key: str | None,
    auth_header: str | None,
    max_retries: int = 0,
) -> bool:
    """Send a single notification to the notification worker queue.

    Args:
        url: Webhook URL to send notification to
        payload: Structured notification payload
        auth_type: Authorization type (NONE, BEARER, API_KEY, CUSTOM_HEADER)
        auth_key: Authorization key/token
        auth_header: Custom header name for CUSTOM_HEADER auth type
        max_retries: Maximum number of retry attempts

    Returns:
        True if task was successfully queued, False otherwise
    """
    try:
        headers = get_webhook_headers(auth_type, auth_key, auth_header)

        # Convert payload to webhook format (excludes internal fields)
        payload_dict = payload.to_webhook_payload()

        # Send task to notification worker
        current_app.send_task(
            "send_webhook_notification",
            args=[
                url,
                payload_dict,
                headers,
                10,  # timeout
            ],
            kwargs={
                "max_retries": max_retries,
                "retry_delay": 10,
            },
            queue="notifications",
        )

        logger.info(
            f"Sent webhook notification to worker queue for {url} (pipeline: {payload.pipeline_id})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send notification to {url}: {e}")
        return False


def trigger_pipeline_notifications(
    api_client,
    pipeline_id: str,
    pipeline_name: str,
    pipeline_type: str,
    status: str,
    execution_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Trigger notifications for pipeline status updates.

    Called by callback worker after successful status update.
    Uses API client to fetch notification configuration.
    """
    # Only send notifications for final states
    if status not in ["SUCCESS", "FAILURE", "COMPLETED", "ERROR", "STOPPED"]:
        logger.debug(f"Skipping notifications for non-final status: {status}")
        return

    try:
        # Fetch pipeline notifications via API
        response = api_client._make_request(
            method="GET",
            endpoint=f"v1/webhook/pipeline/{pipeline_id}/notifications/",
            timeout=10,
        )

        if response.status_code != 200:
            logger.debug(f"No notifications endpoint or data for pipeline {pipeline_id}")
            return

        notifications_data = response.json().get("notifications", [])
        active_notifications = [
            n for n in notifications_data if n.get("is_active", False)
        ]

        if not active_notifications:
            logger.info(f"No active notifications found for pipeline {pipeline_id}")
            return

        # Normalize status for payload
        normalized_status = "SUCCESS" if status in ["SUCCESS", "COMPLETED"] else "FAILURE"

        # Create notification payload
        payload = {
            "type": pipeline_type,
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline_name,
            "status": normalized_status,
            "execution_id": execution_id,
            "error_message": error_message,
        }

        logger.info(
            f"Sending {len(active_notifications)} notifications for pipeline {pipeline_name}"
        )

        # Send each notification
        for notification in active_notifications:
            if notification.get("notification_type") == "WEBHOOK":
                send_notification_to_worker(
                    url=notification["url"],
                    payload=payload,
                    auth_type=notification.get("authorization_type", "NONE"),
                    auth_key=notification.get("authorization_key"),
                    auth_header=notification.get("authorization_header"),
                    max_retries=notification.get("max_retries", 0),
                )
            else:
                logger.debug(
                    f"Skipping non-webhook notification type: {notification.get('notification_type')}"
                )

    except Exception as e:
        logger.error(f"Error triggering pipeline notifications for {pipeline_id}: {e}")


def trigger_api_notifications(
    api_client,
    api_id: str,
    api_name: str,
    status: str,
    execution_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Trigger notifications for API deployment status updates.

    Called by callback worker after successful API status update.
    Uses API client to fetch notification configuration.
    """
    # Only send notifications for final states
    if status not in ["SUCCESS", "FAILURE", "COMPLETED", "ERROR", "STOPPED"]:
        logger.debug(f"Skipping notifications for non-final API status: {status}")
        return

    try:
        # Fetch API notifications via API
        response = api_client._make_request(
            method="GET", endpoint=f"v1/webhook/api/{api_id}/notifications/", timeout=10
        )

        if response.status_code != 200:
            logger.debug(f"No notifications endpoint or data for API {api_id}")
            return

        notifications_data = response.json().get("notifications", [])
        active_notifications = [
            n for n in notifications_data if n.get("is_active", False)
        ]

        if not active_notifications:
            logger.info(f"No active notifications found for API {api_id}")
            return

        # Normalize status for payload
        normalized_status = "SUCCESS" if status in ["SUCCESS", "COMPLETED"] else "FAILURE"

        # Create notification payload
        payload = {
            "type": "API",
            "pipeline_id": api_id,
            "pipeline_name": api_name,
            "status": normalized_status,
            "execution_id": execution_id,
            "error_message": error_message,
        }

        logger.info(
            f"Sending {len(active_notifications)} notifications for API {api_name}"
        )

        # Send each notification
        for notification in active_notifications:
            if notification.get("notification_type") == "WEBHOOK":
                send_notification_to_worker(
                    url=notification["url"],
                    payload=payload,
                    auth_type=notification.get("authorization_type", "NONE"),
                    auth_key=notification.get("authorization_key"),
                    auth_header=notification.get("authorization_header"),
                    max_retries=notification.get("max_retries", 0),
                )
            else:
                logger.debug(
                    f"Skipping non-webhook notification type: {notification.get('notification_type')}"
                )

    except Exception as e:
        logger.error(f"Error triggering API notifications for {api_id}: {e}")


def handle_status_notifications(
    api_client,
    pipeline_id: str,
    status: str,
    execution_id: str | None = None,
    error_message: str | None = None,
    pipeline_name: str | None = None,
    pipeline_type: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Handle notifications for status updates.

    Determines if this is a pipeline or API deployment and triggers appropriate notifications.
    This is the main entry point called by callback worker.

    Args:
        api_client: API client for backend communication
        pipeline_id: Pipeline or API deployment ID
        status: Execution status (string)
        execution_id: Optional execution ID
        error_message: Optional error message for failed executions
        pipeline_name: Optional pipeline/API name
        pipeline_type: Optional workflow type (ETL, API, etc.)
        organization_id: Optional organization context
    """
    try:
        # Convert string status to ExecutionStatus enum
        try:
            execution_status = ExecutionStatus(status)
        except ValueError:
            logger.warning(
                f"Unknown status '{status}', attempting to map to known statuses"
            )
            # Map common status variations
            status_mapping = {
                "SUCCESS": ExecutionStatus.COMPLETED,
                "COMPLETED": ExecutionStatus.COMPLETED,
                "FAILURE": ExecutionStatus.ERROR,
                "FAILED": ExecutionStatus.ERROR,
                "ERROR": ExecutionStatus.ERROR,
                "STOPPED": ExecutionStatus.STOPPED,
            }
            execution_status = status_mapping.get(status.upper())
            if not execution_status:
                logger.error(f"Cannot map status '{status}' to ExecutionStatus enum")
                return

        # Only send notifications for final states
        if not ExecutionStatus.is_completed(execution_status.value):
            logger.debug(f"Skipping notifications for non-final status: {status}")
            return

        # Determine workflow type - default to API if not specified
        workflow_type = WorkflowType.API
        if pipeline_type:
            try:
                workflow_type = WorkflowType(pipeline_type.upper())
            except ValueError:
                logger.warning(
                    f"Unknown workflow type '{pipeline_type}', defaulting to API"
                )

        # Pipeline name MUST exist in models - no fallback allowed
        if not pipeline_name:
            logger.error(
                f"Pipeline name is required but not provided for {workflow_type.value} {pipeline_id}"
            )
            logger.error(
                "Pipeline names must come from Pipeline/APIDeployment models via workflow context"
            )
            return

        logger.debug(f"Using {workflow_type.value} name from model: {pipeline_name}")

        # Create standardized notification payload
        try:
            notification_payload = NotificationPayload.from_execution_status(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_name,
                execution_status=execution_status,
                workflow_type=workflow_type,
                source=NotificationSource.CALLBACK_WORKER,
                execution_id=execution_id,
                error_message=error_message,
                organization_id=organization_id,
            )
        except ValueError as e:
            logger.warning(f"Cannot create notification payload: {e}")
            return

        logger.info(
            f"Processing notification for {workflow_type.value} {pipeline_id} with status {execution_status.value}"
        )

        # TEMPORARY: Send to known webhook URL until internal API endpoints are fixed
        # TODO: Replace with proper notification configuration lookup
        webhook_url = "https://webhook.site/a09c1237-f6e0-461d-942b-16d2bb470660"

        success = send_notification_to_worker(
            url=webhook_url,
            payload=notification_payload,
            auth_type="NONE",
            auth_key=None,
            auth_header=None,
            max_retries=0,
        )

        if success:
            logger.info(
                f"Notification sent successfully for {workflow_type.value} {pipeline_id}"
            )
        else:
            logger.warning(
                f"Failed to send notification for {workflow_type.value} {pipeline_id}"
            )

    except Exception as e:
        logger.error(f"Error handling status notifications for {pipeline_id}: {e}")
        import traceback

        traceback.print_exc()
