"""Lightweight notification helper for callback worker.

Handles notification triggering integrated with status updates.
No Django dependencies, works in pure worker environment.
"""

import logging
from typing import Any

from celery import current_app

# Import shared data models from @unstract/core
from unstract.core.data_models import (
    ExecutionStatus,
    NotificationPayload,
    NotificationSource,
    WorkflowType,
)

logger = logging.getLogger(__name__)

# Mirrors notification_v2.enums.DeliveryMode.BATCHED. Worker stays string-only
# so it does not import Django enums.
DELIVERY_MODE_BATCHED = "BATCHED"
ENQUEUE_BUFFER_ENDPOINT = "v1/webhook/buffer/enqueue/"


def _enqueue_to_buffer(
    api_client: Any,
    notification: dict[str, Any],
    payload: NotificationPayload,
) -> None:
    """POST a single execution event to the backend's buffer endpoint.

    Worker writes nothing to the DB itself — the backend owns NotificationBuffer
    rows. Raises on any failure so the outer trigger_* caller's except block
    logs the drop instead of silently treating BATCHED delivery as successful.
    """
    # Forward the full per-event shape so the backend renderer can match
    # IMMEDIATE's KV layout per event (Type / Pipeline Id / Pipeline Name /
    # Status / Execution Id / Timestamp / Additional Data). Older backend
    # builds that ignore the extra fields stay unaffected.
    payload_type = payload.type.value if hasattr(payload.type, "value") else payload.type
    payload_status = (
        payload.status.value if hasattr(payload.status, "value") else payload.status
    )
    payload_timestamp = payload.timestamp.isoformat() if payload.timestamp else None
    try:
        api_client._make_request(
            method="POST",
            endpoint=ENQUEUE_BUFFER_ENDPOINT,
            data={
                "notification_id": notification["id"],
                "type": payload_type,
                "execution_id": payload.execution_id,
                "pipeline_id": payload.pipeline_id,
                "pipeline_name": payload.pipeline_name,
                "status": payload_status,
                "error_message": payload.error_message,
                "platform": notification.get("platform"),
                "timestamp": payload_timestamp,
                "additional_data": payload.additional_data or {},
            },
            timeout=10,
        )
    except Exception:  # noqa: BLE001 — propagate any failure, don't classify
        logger.exception(
            "Failed to enqueue BATCHED notification %s for pipeline %s",
            notification["id"],
            payload.pipeline_id,
        )
        raise
    logger.info(
        "Enqueued BATCHED notification %s for pipeline %s execution %s",
        notification["id"],
        payload.pipeline_id,
        payload.execution_id,
    )


def _route_notification(
    api_client: Any,
    notification: dict[str, Any],
    payload: NotificationPayload,
) -> None:
    """IMMEDIATE -> existing worker queue; BATCHED -> backend enqueue endpoint.

    Defaults to IMMEDIATE when delivery_mode is missing so older backend
    builds (pre-UNS-611) keep working unchanged.
    """
    if notification.get("notification_type") != "WEBHOOK":
        logger.debug(
            "Skipping non-webhook notification type: %s",
            notification.get("notification_type"),
        )
        return

    if notification.get("delivery_mode") == DELIVERY_MODE_BATCHED:
        try:
            _enqueue_to_buffer(api_client, notification, payload)
        except Exception:  # noqa: BLE001 — already logged with stack inside
            # Surface but don't abort the outer trigger_* loop — sibling
            # BATCHED notifications still deserve their enqueue attempt.
            logger.warning(
                "BATCHED enqueue failed for notification %s; continuing with others",
                notification.get("id"),
            )
        return

    send_notification_to_worker(
        url=notification["url"],
        payload=payload,
        auth_type=notification.get("authorization_type", "NONE"),
        auth_key=notification.get("authorization_key"),
        auth_header=notification.get("authorization_header"),
        max_retries=notification.get("max_retries", 0),
        platform=notification.get("platform"),
    )


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
    platform: str | None = None,
) -> bool:
    """Send a single notification to the notification worker queue.

    Args:
        url: Webhook URL to send notification to
        payload: Structured notification payload
        auth_type: Authorization type (NONE, BEARER, API_KEY, CUSTOM_HEADER)
        auth_key: Authorization key/token
        auth_header: Custom header name for CUSTOM_HEADER auth type
        max_retries: Maximum number of retry attempts
        platform: Platform type from notification config (SLACK, API, etc.)

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
                "platform": platform,
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


def trigger_notification(
    api_client,
    pipeline_id: str,
    pipeline_name: str,
    notification_payload: NotificationPayload,
    execution_id: str | None = None,
) -> None:
    """Trigger notifications for pipeline status updates.

    Called by callback worker after successful status update.
    Uses API client to fetch notification configuration.
    """
    try:
        # Pass execution_id so the backend filter respects notify_on_failures
        # (see trigger_pipeline_notifications for the rationale).
        params = {"execution_id": execution_id} if execution_id else None
        response_data = api_client._make_request(
            method="GET",
            endpoint=f"v1/webhook/pipeline/{pipeline_id}/notifications/",
            params=params,
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

        logger.info(
            f"Sending {len(active_notifications)} notifications for pipeline {pipeline_name}"
        )

        # Send each notification
        for notification in active_notifications:
            _route_notification(api_client, notification, notification_payload)

    except Exception as e:
        logger.error(f"Error triggering pipeline notifications for {pipeline_id}: {e}")


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
    try:
        execution_status = ExecutionStatus(status)
    except Exception as e:
        logger.error(f"Error triggering pipeline notifications for {pipeline_id}: {e}")
        return

    try:
        # Pass execution_id so the backend can drop notify_on_failures=True rows
        # on success runs. Without it the endpoint is a no-op and we'd fire on
        # every active row regardless of trigger preference.
        params = {"execution_id": execution_id} if execution_id else None
        response_data = api_client._make_request(
            method="GET",
            endpoint=f"v1/webhook/pipeline/{pipeline_id}/notifications/",
            params=params,
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

        # Convert pipeline type string to WorkflowType enum
        if pipeline_type == "API":
            workflow_type = WorkflowType.API
        elif pipeline_type == "ETL":
            workflow_type = WorkflowType.ETL
        elif pipeline_type == "TASK":
            workflow_type = WorkflowType.TASK
        else:
            workflow_type = WorkflowType.ETL  # Default fallback

        # File counts come from WorkflowExecution via the same endpoint so
        # webhook receivers (Slack, raw API) see partial-success breakdowns.
        counts = response_data.get("execution_counts") or {}
        payload = NotificationPayload.from_execution_status(
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            execution_status=execution_status,
            workflow_type=workflow_type,
            source=NotificationSource.CALLBACK_WORKER,
            execution_id=execution_id,
            error_message=error_message,
            total_files=counts.get("total_files", 0),
            successful_files=counts.get("successful_files", 0),
            failed_files=counts.get("failed_files", 0),
        )

        logger.info(
            f"Sending {len(active_notifications)} notifications for pipeline {pipeline_name}"
        )

        # Send each notification
        for notification in active_notifications:
            _route_notification(api_client, notification, payload)

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
    try:
        execution_status = ExecutionStatus(status)
    except Exception as e:
        logger.error(f"Error triggering API notifications for {api_id}: {e}")
        return

    try:
        # See trigger_pipeline_notifications: execution_id powers the backend
        # filter that respects notify_on_failures.
        params = {"execution_id": execution_id} if execution_id else None
        response_data = api_client._make_request(
            method="GET",
            endpoint=f"v1/webhook/api/{api_id}/notifications/",
            params=params,
            timeout=10,
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

        counts = response_data.get("execution_counts") or {}
        payload = NotificationPayload.from_execution_status(
            pipeline_id=api_id,
            pipeline_name=api_name,
            execution_status=execution_status,
            workflow_type=WorkflowType.API,
            source=NotificationSource.CALLBACK_WORKER,
            execution_id=execution_id,
            error_message=error_message,
            total_files=counts.get("total_files", 0),
            successful_files=counts.get("successful_files", 0),
            failed_files=counts.get("failed_files", 0),
        )

        logger.info(
            f"Sending {len(active_notifications)} notifications for API {api_name}"
        )

        # Send each notification
        for notification in active_notifications:
            _route_notification(api_client, notification, payload)

    except Exception as e:
        logger.error(f"Error triggering API notifications for {api_id}: {e}")


def handle_status_notifications(
    api_client: Any,
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
