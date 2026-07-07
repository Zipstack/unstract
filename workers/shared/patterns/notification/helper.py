"""Lightweight notification helper for callback worker.

Handles notification triggering integrated with status updates.
No Django dependencies, works in pure worker environment.
"""

import logging
from typing import Any

# Import shared data models from @unstract/core
from unstract.core.data_models import (
    ExecutionStatus,
    NotificationPayload,
    NotificationSource,
    WorkflowType,
)

logger = logging.getLogger(__name__)

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
    # Forward the full per-event shape so the backend can buffer it and the
    # shared clubbed renderer can format each event consistently. Older backend
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
    # Propagate any failure; caller decides whether to continue iteration.
    except Exception:  # noqa: BLE001
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
    """Forward webhook notifications to the backend buffer-enqueue endpoint.

    Single dispatch path: the backend owns the buffer and the periodic
    flush ships clubbed messages. Non-webhook notification types are
    skipped at this layer. An enqueue failure is logged but doesn't abort
    the outer trigger_* loop so sibling notifications still get their
    chance.
    """
    if notification.get("notification_type") != "WEBHOOK":
        logger.debug(
            "Skipping non-webhook notification type: %s",
            notification.get("notification_type"),
        )
        return

    try:
        _enqueue_to_buffer(api_client, notification, payload)
    # Already logged with stack inside _enqueue_to_buffer; broad catch keeps
    # sibling notifications going. Emit a metric so a dropped failure alert is
    # observable here (this is the path's final swallow point).
    except Exception:  # noqa: BLE001
        logger.warning(
            "metric=notification_dropped_total notification_id=%s; "
            "buffer enqueue failed, continuing with others",
            notification.get("id"),
        )


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


def notify_execution_failure(
    api_client: Any,
    pipeline_id: str,
    execution_id: str,
    organization_id: str,
    error_message: str | None = None,
) -> None:
    """Dispatch a failure notification for a run that errored *before* the
    file-processing callback ran.

    ETL/Task notifications normally fire from the callback worker's
    ``handle_status_notifications`` once files finish processing. Build/setup
    failures — missing-tool / tool-registry errors, tool validation, source
    connector errors — halt the run before any file is processed, so that
    callback never runs and a "notify on failures" subscriber hears nothing.
    This resolves the pipeline's name/type from the backend and reuses the
    standard dispatch with a terminal ERROR status, so the failure-filter and
    the clubbed payload are identical to the normal path.

    Mutually exclusive with the callback: a run that reaches file processing
    returns normally from the worker and is notified by the callback instead.
    API deployments are intentionally not handled here — they already dispatch
    early failures through the backend ``update_pipeline_status`` path.
    """
    try:
        api_client.set_organization_context(organization_id)
        response = api_client.get_pipeline_data(
            pipeline_id=pipeline_id, check_active=False
        )
        if not (getattr(response, "success", False) and response.data):
            logger.warning(
                "Skipping early-failure notification for %s: pipeline data unavailable",
                pipeline_id,
            )
            return
        # Unified endpoint nests the record under "pipeline"; fall back to the
        # flat shape for older builds.
        pdata = response.data.get("pipeline", response.data)
        pipeline_name = pdata.get("pipeline_name") or pdata.get("api_name")
        pipeline_type = pdata.get("pipeline_type", WorkflowType.ETL.value)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Could not resolve pipeline %s for early-failure notification: %s",
            pipeline_id,
            e,
        )
        return

    handle_status_notifications(
        api_client=api_client,
        pipeline_id=pipeline_id,
        status=ExecutionStatus.ERROR.value,
        execution_id=execution_id,
        error_message=error_message,
        pipeline_name=pipeline_name,
        pipeline_type=pipeline_type,
        organization_id=organization_id,
    )
