"""IDE Callback Worker Tasks

Post-execution callbacks for Prompt Studio IDE operations.
These tasks run on the workers image (no Django) and use InternalAPIClient
to persist state through the backend's internal API endpoints.

Task names are preserved exactly to maintain Celery routing compatibility.
"""

import json
import logging
import time
import uuid
from datetime import date, datetime
from typing import Any

from celery import current_app as app
from shared.clients.prompt_studio_client import PromptStudioAPIClient

logger = logging.getLogger(__name__)

PROMPT_STUDIO_RESULT_EVENT = "prompt_studio_result"

# WebSocket emission endpoint (relative to internal API base)
_EMIT_WEBSOCKET_ENDPOINT = "emit-websocket/"


class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that converts uuid.UUID and datetime objects to strings."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def _json_safe(data: Any) -> Any:
    """Round-trip through JSON to convert non-serializable types."""
    return json.loads(json.dumps(data, cls=_SafeEncoder))


def _get_api_client() -> PromptStudioAPIClient:
    """Create a PromptStudioAPIClient for internal API calls."""
    return PromptStudioAPIClient()


def _emit_websocket(
    api_client: PromptStudioAPIClient,
    room: str,
    event: str,
    data: dict[str, Any],
) -> None:
    """Emit a WebSocket event via the backend's internal emit-websocket endpoint."""
    try:
        payload = {"room": room, "event": event, "data": data}
        api_client.post(_EMIT_WEBSOCKET_ENDPOINT, data=payload)
    except Exception as e:
        logger.error("Failed to emit WebSocket event: %s", e)


def _emit_event(
    api_client: PromptStudioAPIClient,
    log_events_id: str,
    task_id: str,
    operation: str,
    tool_id: str = "",
    extra: dict[str, Any] | None = None,
    **event_fields: Any,
) -> None:
    """Push a Socket.IO event (success or failure) to the frontend.

    Common fields (task_id, operation, tool_id) are always included.
    Pass ``status="completed", result=...`` for success events, or
    ``status="failed", error=...`` for failure events via *event_fields*.
    """
    payload: dict[str, Any] = {
        "task_id": task_id,
        "operation": operation,
        "tool_id": tool_id,
        **event_fields,
    }
    if extra:
        payload.update(extra)
    _emit_websocket(
        api_client,
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=_json_safe(payload),
    )


def _get_task_error(failed_task_id: str, default: str) -> str:
    """Retrieve the error message from a failed Celery task's result backend."""
    try:
        from celery.result import AsyncResult

        res = AsyncResult(failed_task_id, app=app)
        if res.result:
            return str(res.result)
    except Exception:
        pass
    return default


def _track_subscription_usage(org_id: str, run_id: str) -> None:
    """Commit deferred subscription usage for an IDE execution.
    Non-blocking: errors are logged but do not fail the callback.
    """
    if not org_id or not run_id:
        return
    try:
        from client_plugin_registry import get_client_plugin

        subscription_plugin = get_client_plugin("subscription_usage")
        if not subscription_plugin:
            return
        result = subscription_plugin.commit_batch_subscription_usage(
            organization_id=org_id,
            file_execution_ids=[run_id],
        )
        logger.info("IDE subscription usage committed for run_id=%s: %s", run_id, result)
    except Exception:
        logger.error(
            "Failed to commit IDE subscription usage for run_id=%s (continuing callback)",
            run_id,
            exc_info=True,
        )


# ------------------------------------------------------------------
# IDE Callback Tasks
#
# These are fire-and-forget callbacks invoked by Celery link/link_error
# after the executor worker finishes. They run on the ide_callback queue
# and use InternalAPIClient for ORM persistence.
# ------------------------------------------------------------------


@app.task(name="ide_index_complete")
def ide_index_complete(
    result_dict: dict[str, Any],
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery link callback after successful ide_index execution.

    Performs post-indexing bookkeeping via internal API and pushes
    a socket event to the frontend.
    """
    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    org_id = cb.get("org_id", "")
    user_id = cb.get("user_id", "")
    document_id = cb.get("document_id", "")
    doc_id_key = cb.get("doc_id_key", "")
    profile_manager_id = cb.get("profile_manager_id")
    executor_task_id = cb.get("executor_task_id", "")
    tool_id = cb.get("tool_id", "")
    run_id = cb.get("run_id", "")

    api = _get_api_client()

    try:
        # Check executor-level failure
        if not result_dict.get("success", False):
            error_msg = result_dict.get("error", "Unknown executor error")
            logger.error("ide_index executor reported failure: %s", error_msg)
            api.remove_document_indexing(
                org_id=org_id,
                user_id=user_id,
                doc_id_key=doc_id_key,
                organization_id=org_id,
            )
            _emit_event(
                api,
                log_events_id,
                executor_task_id,
                "index_document",
                tool_id=tool_id,
                extra={"document_id": document_id},
                status="failed",
                error=error_msg,
            )
            return {"status": "failed", "error": error_msg}

        doc_id = result_dict.get("data", {}).get("doc_id", doc_id_key)

        # Mark document as indexed in cache
        api.mark_document_indexed(
            org_id=org_id,
            user_id=user_id,
            doc_id_key=doc_id_key,
            doc_id=doc_id,
            organization_id=org_id,
        )

        # Update index manager ORM record
        if profile_manager_id:
            try:
                api.update_index_manager(
                    document_id=document_id,
                    profile_manager_id=profile_manager_id,
                    doc_id=doc_id,
                    organization_id=org_id,
                )
            except Exception:
                logger.warning(
                    "Failed to update index manager for profile %s; "
                    "primary indexing succeeded.",
                    profile_manager_id,
                )

        # Handle summary index tracking via backend endpoint
        # (requires PromptIdeBaseTool + IndexingUtils which need Django ORM)
        summary_profile_id = cb.get("summary_profile_id", "")
        summarize_file_path = cb.get("summarize_file_path", "")

        if summary_profile_id and summarize_file_path:
            try:
                resp = api.get_summary_index_key(
                    summary_profile_id=summary_profile_id,
                    summarize_file_path=summarize_file_path,
                    org_id=org_id,
                    organization_id=org_id,
                )
                if resp.get("success"):
                    summarize_doc_id = resp["data"]["doc_id"]
                    api.update_index_manager(
                        document_id=document_id,
                        profile_manager_id=summary_profile_id,
                        doc_id=summarize_doc_id,
                        is_summary=True,
                        organization_id=org_id,
                    )
            except Exception:
                logger.exception(
                    "Failed to update summary index manager for document %s; "
                    "primary indexing succeeded.",
                    document_id,
                )

        _track_subscription_usage(org_id, run_id)

        result: dict[str, Any] = {
            "message": "Document indexed successfully.",
            "document_id": document_id,
        }
        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            "index_document",
            tool_id=tool_id,
            status="completed",
            result=result,
        )
        return result

    except Exception as e:
        logger.exception("ide_index_complete callback failed")
        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            "index_document",
            tool_id=tool_id,
            extra={"document_id": document_id},
            status="failed",
            error=str(e),
        )
        raise


@app.task(name="ide_index_error")
def ide_index_error(
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> None:
    """Celery link_error callback when an ide_index task fails.

    Cleans up the indexing-in-progress flag and pushes an error socket event.
    """
    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    org_id = cb.get("org_id", "")
    user_id = cb.get("user_id", "")
    document_id = cb.get("document_id", "")
    doc_id_key = cb.get("doc_id_key", "")
    executor_task_id = cb.get("executor_task_id", "")
    tool_id = cb.get("tool_id", "")

    api = _get_api_client()

    try:
        error_msg = _get_task_error(failed_task_id, default="Indexing failed")

        # Clean up the indexing-in-progress flag
        if doc_id_key:
            api.remove_document_indexing(
                org_id=org_id,
                user_id=user_id,
                doc_id_key=doc_id_key,
                organization_id=org_id,
            )

        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            "index_document",
            tool_id=tool_id,
            extra={"document_id": document_id},
            status="failed",
            error=error_msg,
        )
    except Exception:
        logger.exception("ide_index_error callback failed")


@app.task(name="ide_prompt_complete")
def ide_prompt_complete(
    result_dict: dict[str, Any],
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery link callback after successful answer_prompt / single_pass execution.

    Persists prompt outputs via internal API and pushes a socket event.
    """
    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    org_id = cb.get("org_id", "")
    operation = cb.get("operation", "fetch_response")
    run_id = cb.get("run_id", "")
    document_id = cb.get("document_id", "")
    prompt_ids = cb.get("prompt_ids", [])
    profile_manager_id = cb.get("profile_manager_id")
    is_single_pass = cb.get("is_single_pass", False)
    executor_task_id = cb.get("executor_task_id", "")
    tool_id = cb.get("tool_id", "")
    dispatch_time = cb.get("dispatch_time", 0)

    api = _get_api_client()

    try:
        # Check executor-level failure
        if not result_dict.get("success", False):
            error_msg = result_dict.get("error", "Unknown executor error")
            logger.error("ide_prompt executor reported failure: %s", error_msg)
            _emit_event(
                api,
                log_events_id,
                executor_task_id,
                operation,
                tool_id=tool_id,
                extra={
                    "prompt_ids": prompt_ids,
                    "document_id": document_id,
                    "profile_manager_id": profile_manager_id,
                },
                status="failed",
                error=error_msg,
            )
            return {"status": "failed", "error": error_msg}

        data = result_dict.get("data", {})
        outputs = _json_safe(data.get("output", {}))
        metadata = _json_safe(data.get("metadata", {}))

        logger.info(
            "ide_prompt_complete: operation=%s output_keys=%s prompt_ids=%s "
            "doc=%s profile=%s",
            operation,
            list(outputs.keys()) if isinstance(outputs, dict) else type(outputs).__name__,
            prompt_ids,
            document_id,
            profile_manager_id,
        )

        # Persist outputs via internal API
        resp = api.update_prompt_output(
            run_id=run_id,
            prompt_ids=prompt_ids,
            outputs=outputs,
            document_id=document_id,
            is_single_pass_extract=is_single_pass,
            metadata=metadata,
            profile_manager_id=profile_manager_id,
            organization_id=org_id,
        )
        response = resp.get("data", []) if resp.get("success") else []

        _track_subscription_usage(org_id, run_id)

        # Fire HubSpot event if applicable
        hubspot_user_id = cb.get("hubspot_user_id")
        if hubspot_user_id:
            try:
                api.notify_hubspot(
                    user_id=hubspot_user_id,
                    event_name="PROMPT_RUN",
                    is_first_for_org=cb.get("is_first_prompt_run", False),
                    action_label="prompt run",
                    organization_id=org_id,
                )
            except Exception:
                logger.warning("Failed to send HubSpot PROMPT_RUN event", exc_info=True)

        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            operation,
            tool_id=tool_id,
            extra={
                "prompt_ids": prompt_ids,
                "document_id": document_id,
                "profile_manager_id": profile_manager_id,
                "elapsed": int(time.time() - dispatch_time) if dispatch_time else 0,
            },
            status="completed",
            result=response,
        )
        # Return minimal status to avoid logging sensitive extracted data
        return {"status": "completed", "operation": operation}

    except Exception as e:
        logger.exception("ide_prompt_complete callback failed")
        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            operation,
            tool_id=tool_id,
            extra={
                "prompt_ids": prompt_ids,
                "document_id": document_id,
                "profile_manager_id": profile_manager_id,
            },
            status="failed",
            error=str(e),
        )
        raise


@app.task(name="ide_prompt_error")
def ide_prompt_error(
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> None:
    """Celery link_error callback when an answer_prompt / single_pass task fails.

    Pushes an error socket event to the frontend.
    """
    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    operation = cb.get("operation", "fetch_response")
    executor_task_id = cb.get("executor_task_id", "")
    tool_id = cb.get("tool_id", "")

    api = _get_api_client()

    try:
        error_msg = _get_task_error(failed_task_id, default="Prompt execution failed")

        _emit_event(
            api,
            log_events_id,
            executor_task_id,
            operation,
            tool_id=tool_id,
            extra={
                "prompt_ids": cb.get("prompt_ids", []),
                "document_id": cb.get("document_id", ""),
                "profile_manager_id": cb.get("profile_manager_id"),
            },
            status="failed",
            error=error_msg,
        )
    except Exception:
        logger.exception("ide_prompt_error callback failed")
