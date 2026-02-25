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


# ------------------------------------------------------------------
# Phase 5B — Fire-and-forget callback tasks
#
# These are lightweight callbacks invoked by Celery `link` / `link_error`
# after the executor worker finishes.  They run on the backend
# (celery_prompt_studio queue) and do only post-ORM writes + socket
# emission — no heavy computation.
# ------------------------------------------------------------------


@shared_task(name="ide_index_complete")
def ide_index_complete(
    result_dict: dict[str, Any],
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery ``link`` callback after a successful ``ide_index`` execution.

    Performs post-indexing ORM bookkeeping and pushes a socket event to
    the frontend.
    """
    from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
        DocumentIndexingService,
    )
    from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (
        PromptStudioIndexHelper,
    )
    from prompt_studio.prompt_profile_manager_v2.models import ProfileManager

    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    request_id = cb.get("request_id", "")
    org_id = cb.get("org_id", "")
    user_id = cb.get("user_id", "")
    document_id = cb.get("document_id", "")
    doc_id_key = cb.get("doc_id_key", "")
    profile_manager_id = cb.get("profile_manager_id")
    executor_task_id = cb.get("executor_task_id", "")

    try:
        _setup_state_store(log_events_id, request_id, org_id)

        # Check executor-level failure
        if not result_dict.get("success", False):
            error_msg = result_dict.get("error", "Unknown executor error")
            logger.error("ide_index executor reported failure: %s", error_msg)
            DocumentIndexingService.remove_document_indexing(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )
            _emit_error(
                log_events_id,
                executor_task_id,
                "index_document",
                error_msg,
                extra={"document_id": document_id},
            )
            return {"status": "failed", "error": error_msg}

        doc_id = result_dict.get("data", {}).get("doc_id", doc_id_key)

        # ORM writes
        DocumentIndexingService.mark_document_indexed(
            org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
        )
        if profile_manager_id:
            profile_manager = ProfileManager.objects.get(pk=profile_manager_id)
            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )

        result: dict[str, Any] = {
            "message": "Document indexed successfully.",
            "document_id": document_id,
        }
        _emit_result(log_events_id, executor_task_id, "index_document", result)
        return result
    except Exception as e:
        logger.exception("ide_index_complete callback failed")
        _emit_error(
            log_events_id,
            executor_task_id,
            "index_document",
            str(e),
            extra={"document_id": document_id},
        )
        raise
    finally:
        _clear_state_store()


@shared_task(name="ide_index_error")
def ide_index_error(
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> None:
    """Celery ``link_error`` callback when an ``ide_index`` task fails.

    Cleans up the indexing-in-progress flag and pushes an error socket
    event to the frontend.
    """
    from celery.result import AsyncResult

    from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
        DocumentIndexingService,
    )

    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    request_id = cb.get("request_id", "")
    org_id = cb.get("org_id", "")
    user_id = cb.get("user_id", "")
    document_id = cb.get("document_id", "")
    doc_id_key = cb.get("doc_id_key", "")
    executor_task_id = cb.get("executor_task_id", "")

    try:
        _setup_state_store(log_events_id, request_id, org_id)

        # Attempt to retrieve the actual exception from the result backend
        error_msg = "Indexing failed"
        try:
            from backend.worker_celery import get_worker_celery_app

            res = AsyncResult(failed_task_id, app=get_worker_celery_app())
            if res.result:
                error_msg = str(res.result)
        except Exception:
            pass

        # Clean up the indexing-in-progress flag
        if doc_id_key:
            DocumentIndexingService.remove_document_indexing(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )

        _emit_error(
            log_events_id,
            executor_task_id,
            "index_document",
            error_msg,
            extra={"document_id": document_id},
        )
    except Exception:
        logger.exception("ide_index_error callback failed")
    finally:
        _clear_state_store()


@shared_task(name="ide_prompt_complete")
def ide_prompt_complete(
    result_dict: dict[str, Any],
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery ``link`` callback after a successful answer_prompt / single_pass
    execution.

    Persists prompt outputs via OutputManagerHelper and pushes a socket
    event.
    """
    from prompt_studio.prompt_studio_output_manager_v2.output_manager_helper import (
        OutputManagerHelper,
    )
    from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    request_id = cb.get("request_id", "")
    org_id = cb.get("org_id", "")
    operation = cb.get("operation", "fetch_response")
    run_id = cb.get("run_id", "")
    document_id = cb.get("document_id", "")
    prompt_ids = cb.get("prompt_ids", [])
    profile_manager_id = cb.get("profile_manager_id")
    is_single_pass = cb.get("is_single_pass", False)
    executor_task_id = cb.get("executor_task_id", "")

    try:
        _setup_state_store(log_events_id, request_id, org_id)

        # Check executor-level failure
        if not result_dict.get("success", False):
            error_msg = result_dict.get("error", "Unknown executor error")
            logger.error("ide_prompt executor reported failure: %s", error_msg)
            _emit_error(log_events_id, executor_task_id, operation, error_msg)
            return {"status": "failed", "error": error_msg}

        data = result_dict.get("data", {})

        # Re-fetch prompt ORM objects for OutputManagerHelper
        prompts = list(
            ToolStudioPrompt.objects.filter(prompt_id__in=prompt_ids).order_by(
                "sequence_number"
            )
        )

        response = OutputManagerHelper.handle_prompt_output_update(
            run_id=run_id,
            prompts=prompts,
            outputs=data.get("output", []),
            document_id=document_id,
            is_single_pass_extract=is_single_pass,
            profile_manager_id=profile_manager_id,
            metadata=data.get("metadata", {}),
        )

        _emit_result(log_events_id, executor_task_id, operation, response)
        return response
    except Exception as e:
        logger.exception("ide_prompt_complete callback failed")
        _emit_error(log_events_id, executor_task_id, operation, str(e))
        raise
    finally:
        _clear_state_store()


@shared_task(name="ide_prompt_error")
def ide_prompt_error(
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> None:
    """Celery ``link_error`` callback when an answer_prompt / single_pass
    task fails.

    Pushes an error socket event to the frontend.
    """
    from celery.result import AsyncResult

    cb = callback_kwargs or {}
    log_events_id = cb.get("log_events_id", "")
    request_id = cb.get("request_id", "")
    org_id = cb.get("org_id", "")
    operation = cb.get("operation", "fetch_response")
    executor_task_id = cb.get("executor_task_id", "")

    try:
        _setup_state_store(log_events_id, request_id, org_id)

        error_msg = "Prompt execution failed"
        try:
            from backend.worker_celery import get_worker_celery_app

            res = AsyncResult(failed_task_id, app=get_worker_celery_app())
            if res.result:
                error_msg = str(res.result)
        except Exception:
            pass

        _emit_error(log_events_id, executor_task_id, operation, error_msg)
    except Exception:
        logger.exception("ide_prompt_error callback failed")
    finally:
        _clear_state_store()


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
