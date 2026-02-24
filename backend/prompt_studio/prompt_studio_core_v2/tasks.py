import json
import logging
import uuid
from typing import Any

from celery import shared_task

from account_v2.constants import Common
from utils.constants import Account
from utils.local_context import StateStore
from utils.log_events import _emit_websocket_event

logger = logging.getLogger(__name__)

PROMPT_STUDIO_RESULT_EVENT = "prompt_studio_result"


class _UUIDEncoder(json.JSONEncoder):
    """JSON encoder that converts uuid.UUID objects to strings."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


def _json_safe(data: Any) -> Any:
    """Round-trip through JSON to convert non-serializable types (UUID → str).

    DRF serializers return uuid.UUID objects for PrimaryKeyRelatedField
    and UUIDField. Socket.IO's pubsub uses stdlib json.dumps which
    cannot handle them, so we sanitize here before emitting.
    """
    return json.loads(json.dumps(data, cls=_UUIDEncoder))


def _setup_state_store(
    log_events_id: str, request_id: str, org_id: str = ""
) -> None:
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
) -> None:
    """Push a success event to the frontend via Socket.IO."""
    _emit_websocket_event(
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=_json_safe({
            "task_id": task_id,
            "status": "completed",
            "operation": operation,
            "result": result,
        }),
    )


def _emit_error(
    log_events_id: str,
    task_id: str,
    operation: str,
    error: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Push a failure event to the frontend via Socket.IO."""
    data: dict[str, Any] = {
        "task_id": task_id,
        "status": "failed",
        "operation": operation,
        "error": error,
    }
    if extra:
        data.update(extra)
    _emit_websocket_event(
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=data,
    )


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
        _emit_result(log_events_id, self.request.id, "index_document", result)
        return result
    except Exception as e:
        logger.exception("run_index_document failed")
        _emit_error(
            log_events_id,
            self.request.id,
            "index_document",
            str(e),
            extra={"document_id": document_id},
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
        _emit_result(log_events_id, self.request.id, "fetch_response", response)
        return response
    except Exception as e:
        logger.exception("run_fetch_response failed")
        _emit_error(log_events_id, self.request.id, "fetch_response", str(e))
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
            log_events_id, self.request.id, "single_pass_extraction", response
        )
        return response
    except Exception as e:
        logger.exception("run_single_pass_extraction failed")
        _emit_error(
            log_events_id, self.request.id, "single_pass_extraction", str(e)
        )
        raise
    finally:
        _clear_state_store()
