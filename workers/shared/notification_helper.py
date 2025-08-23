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
        response_data = api_client._make_request(
            method="GET",
            endpoint=f"v1/webhook/pipeline/{pipeline_id}/notifications/",
            timeout=10,
        )

        # _make_request already handles status codes and returns parsed data
        # If we get here, the request was successful (status 200)
        notifications_data = response_data.get("notifications", [])
        active_notifications = [
            n for n in notifications_data if n.get("is_active", False)
        ]

        if not active_notifications:
            logger.info(f"No active notifications found for pipeline {pipeline_id}")
            return

        # Normalize status for payload
        normalized_status = "SUCCESS" if status in ["SUCCESS", "COMPLETED"] else "FAILURE"
        execution_status = (
            ExecutionStatus.COMPLETED
            if normalized_status == "SUCCESS"
            else ExecutionStatus.FAILED
        )

        # Convert pipeline type string to WorkflowType enum
        if pipeline_type == "API":
            workflow_type = WorkflowType.API
        elif pipeline_type == "ETL":
            workflow_type = WorkflowType.ETL
        elif pipeline_type == "TASK":
            workflow_type = WorkflowType.TASK
        else:
            workflow_type = WorkflowType.ETL  # Default fallback

        # Create notification payload using dataclass
        payload = NotificationPayload.from_execution_status(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            execution_status=execution_status,
            workflow_type=workflow_type,
            source=NotificationSource.CALLBACK_WORKER,
            execution_id=execution_id,
            error_message=error_message,
        )

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
        response_data = api_client._make_request(
            method="GET", endpoint=f"v1/webhook/api/{api_id}/notifications/", timeout=10
        )

        # _make_request already handles status codes and returns parsed data
        # If we get here, the request was successful (status 200)
        notifications_data = response_data.get("notifications", [])
        active_notifications = [
            n for n in notifications_data if n.get("is_active", False)
        ]

        if not active_notifications:
            logger.info(f"No active notifications found for API {api_id}")
            return

        # Normalize status for payload
        normalized_status = "SUCCESS" if status in ["SUCCESS", "COMPLETED"] else "FAILURE"
        execution_status = (
            ExecutionStatus.COMPLETED
            if normalized_status == "SUCCESS"
            else ExecutionStatus.FAILED
        )

        # Create notification payload using dataclass
        payload = NotificationPayload.from_execution_status(
            pipeline_id=api_id,
            pipeline_name=api_name,
            execution_status=execution_status,
            workflow_type=WorkflowType.API,
            source=NotificationSource.CALLBACK_WORKER,
            execution_id=execution_id,
            error_message=error_message,
        )

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

        # DEBUG: Log input parameters
        logger.info(
            f"DEBUG: handle_status_notifications called with pipeline_id='{pipeline_id}', pipeline_name='{pipeline_name}', pipeline_type='{pipeline_type}', status='{status}'"
        )

        # Determine workflow type - default to API if not specified
        workflow_type = WorkflowType.API
        if pipeline_type:
            try:
                logger.info(
                    f"DEBUG: Converting pipeline_type '{pipeline_type}' to WorkflowType enum"
                )
                workflow_type = WorkflowType(pipeline_type.upper())
                logger.info(
                    f"DEBUG: Successfully converted to workflow_type='{workflow_type.value}'"
                )
            except ValueError:
                logger.warning(
                    f"Unknown workflow type '{pipeline_type}', defaulting to API"
                )
        else:
            logger.info(
                "DEBUG: No pipeline_type provided, using default workflow_type=API"
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

        # Validate execution status for notifications
        try:
            # Just validate the status can be converted - we use separate functions below
            NotificationPayload.from_execution_status(
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

        # Use proper notification configuration lookup based on workflow type
        try:
            if workflow_type == WorkflowType.API:
                trigger_api_notifications(
                    api_client=api_client,
                    api_id=pipeline_id,
                    api_name=pipeline_name,
                    status=status,
                    execution_id=execution_id,
                    error_message=error_message,
                )
            else:
                # For ETL/TASK/other pipeline types
                trigger_pipeline_notifications(
                    api_client=api_client,
                    pipeline_id=pipeline_id,
                    pipeline_name=pipeline_name,
                    pipeline_type=workflow_type.value,
                    status=status,
                    execution_id=execution_id,
                    error_message=error_message,
                )

            logger.info(
                f"Notification sent successfully for {workflow_type.value} {pipeline_id}"
            )
        except Exception as notification_error:
            logger.warning(
                f"Failed to send notification for {workflow_type.value} {pipeline_id}: {notification_error}"
            )

    except Exception as e:
        logger.error(f"Error handling status notifications for {pipeline_id}: {e}")
        import traceback

        traceback.print_exc()
