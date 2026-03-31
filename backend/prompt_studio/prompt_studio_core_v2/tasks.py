import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from account_v2.constants import Common
from celery import shared_task
from utils.constants import Account
from utils.local_context import StateStore

logger = logging.getLogger(__name__)

PROMPT_STUDIO_RESULT_EVENT = "prompt_studio_result"


class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that converts uuid.UUID and datetime objects to strings."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def _json_safe(data: Any) -> Any:
    """Round-trip through JSON to convert non-serializable types.

    Handles uuid.UUID (from DRF serializers) and datetime/date objects
    (from plugins or ORM fields) that stdlib json.dumps cannot handle.
    """
    return json.loads(json.dumps(data, cls=_SafeEncoder))


def _setup_state_store(log_events_id: str, request_id: str, org_id: str = "") -> None:
    """Restore thread-local context that was captured in the Django view."""
    StateStore.set(Common.LOG_EVENTS_ID, log_events_id)
    StateStore.set(Common.REQUEST_ID, request_id)
    if org_id:
        StateStore.set(Account.ORGANIZATION_ID, org_id)


def _clear_state_store() -> None:
    """Clean up thread-local context to prevent leaking between tasks."""
    StateStore.clear(Common.LOG_EVENTS_ID)
    StateStore.clear(Common.REQUEST_ID)
    StateStore.clear(Account.ORGANIZATION_ID)


def _emit_result(
    log_events_id: str,
    task_id: str,
    operation: str,
    result: dict[str, Any],
    tool_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Push a success event to the frontend via Socket.IO."""
    from utils.log_events import (
        _emit_websocket_event,  # Lazy import: task module loaded before Django apps ready
    )

    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": "completed",
        "operation": operation,
        "result": result,
        "tool_id": tool_id,
    }
    if extra:
        payload.update(extra)
    _emit_websocket_event(
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=_json_safe(payload),
    )


def _emit_error(
    log_events_id: str,
    task_id: str,
    operation: str,
    error: str,
    extra: dict[str, Any] | None = None,
    tool_id: str = "",
) -> None:
    """Push a failure event to the frontend via Socket.IO."""
    from utils.log_events import (
        _emit_websocket_event,  # Lazy import: task module loaded before Django apps ready
    )

    data: dict[str, Any] = {
        "task_id": task_id,
        "status": "failed",
        "operation": operation,
        "error": error,
        "tool_id": tool_id,
    }
    if extra:
        data.update(extra)
    _emit_websocket_event(
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=data,
    )


# ------------------------------------------------------------------
# IDE callback tasks (ide_index_complete, ide_index_error,
# ide_prompt_complete, ide_prompt_error) have been moved to the
# standalone ide_callback worker (workers/ide_callback/tasks.py).
# They now run on the workers image using InternalAPIClient.
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Legacy tasks (kept for backward compatibility during rollout)
# ------------------------------------------------------------------


@shared_task(name="prompt_studio_index_document", bind=True)
def run_index_document(
    self,
    tool_id: str,
    file_name: str,
    org_id: str,
    user_id: str,
    document_id: str,
    run_id: str,
    log_events_id: str,
    request_id: str,
) -> dict[str, Any]:
    # Lazy import: circular dep (helper <-> tasks)
    from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import (
        PromptStudioHelper,
    )

    try:
        _setup_state_store(log_events_id, request_id, org_id)
        PromptStudioHelper.index_document(
            tool_id=tool_id,
            file_name=file_name,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
        )
        result: dict[str, Any] = {
            "message": "Document indexed successfully.",
            "document_id": document_id,
        }
        _emit_result(
            log_events_id,
            self.request.id,
            "index_document",
            result,
            tool_id=tool_id,
        )
        return result
    except Exception as e:
        logger.exception("run_index_document failed")
        _emit_error(
            log_events_id,
            self.request.id,
            "index_document",
            str(e),
            extra={"document_id": document_id},
            tool_id=tool_id,
        )
        raise
    finally:
        _clear_state_store()


@shared_task(name="prompt_studio_fetch_response", bind=True)
def run_fetch_response(
    self,
    tool_id: str,
    org_id: str,
    user_id: str,
    document_id: str,
    run_id: str,
    log_events_id: str,
    request_id: str,
    id: str | None = None,
    profile_manager_id: str | None = None,
) -> dict[str, Any]:
    # Lazy import: circular dep (helper <-> tasks)
    from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import (
        PromptStudioHelper,
    )

    try:
        _setup_state_store(log_events_id, request_id, org_id)
        response: dict[str, Any] = PromptStudioHelper.prompt_responder(
            id=id,
            tool_id=tool_id,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
            profile_manager_id=profile_manager_id,
        )
        _emit_result(
            log_events_id,
            self.request.id,
            "fetch_response",
            response,
            tool_id=tool_id,
        )
        # Return minimal status to avoid logging sensitive extracted data
        return {"status": "completed", "operation": "fetch_response"}
    except Exception as e:
        logger.exception("run_fetch_response failed")
        _emit_error(
            log_events_id,
            self.request.id,
            "fetch_response",
            str(e),
            tool_id=tool_id,
        )
        raise
    finally:
        _clear_state_store()


@shared_task(name="prompt_studio_single_pass", bind=True)
def run_single_pass_extraction(
    self,
    tool_id: str,
    org_id: str,
    user_id: str,
    document_id: str,
    run_id: str,
    log_events_id: str,
    request_id: str,
) -> dict[str, Any]:
    # Lazy import: circular dep (helper <-> tasks)
    from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import (
        PromptStudioHelper,
    )

    try:
        _setup_state_store(log_events_id, request_id, org_id)
        response: dict[str, Any] = PromptStudioHelper.prompt_responder(
            tool_id=tool_id,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
        )
        _emit_result(
            log_events_id,
            self.request.id,
            "single_pass_extraction",
            response,
            tool_id=tool_id,
        )
        # Return minimal status to avoid logging sensitive extracted data
        return {"status": "completed", "operation": "single_pass_extraction"}
    except Exception as e:
        logger.exception("run_single_pass_extraction failed")
        _emit_error(
            log_events_id,
            self.request.id,
            "single_pass_extraction",
            str(e),
            tool_id=tool_id,
        )
        raise
    finally:
        _clear_state_store()
