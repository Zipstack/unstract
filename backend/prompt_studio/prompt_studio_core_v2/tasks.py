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
) -> None:
    """Push a success event to the frontend via Socket.IO."""
    from utils.log_events import _emit_websocket_event

    _emit_websocket_event(
        room=log_events_id,
        event=PROMPT_STUDIO_RESULT_EVENT,
        data=_json_safe(
            {
                "task_id": task_id,
                "status": "completed",
                "operation": operation,
                "result": result,
            }
        ),
    )


def _emit_error(
    log_events_id: str,
    task_id: str,
    operation: str,
    error: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Push a failure event to the frontend via Socket.IO."""
    from utils.log_events import _emit_websocket_event

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
# (prompt_studio_callback queue) and do only post-ORM writes + socket
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
    from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
    from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
        DocumentIndexingService,
    )
    from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (
        PromptStudioIndexHelper,
    )

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

        # Fetch profile manager before ORM writes so a missing profile
        # doesn't leave partial state.
        profile_manager = None
        if profile_manager_id:
            try:
                profile_manager = ProfileManager.objects.get(pk=profile_manager_id)
            except ProfileManager.DoesNotExist:
                logger.warning(
                    "ProfileManager %s not found during ide_index_complete; "
                    "skipping index manager update.",
                    profile_manager_id,
                )

        # ORM writes
        DocumentIndexingService.mark_document_indexed(
            org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
        )
        if profile_manager:
            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )

        # Handle summarize index tracking (summary was generated by executor)
        summary_profile_id = cb.get("summary_profile_id", "")
        summarize_file_path = cb.get("summarize_file_path", "")

        if summary_profile_id and summarize_file_path:
            try:
                from unstract.sdk1.constants import LogLevel
                from unstract.sdk1.file_storage.constants import StorageType
                from unstract.sdk1.file_storage.env_helper import EnvHelper
                from unstract.sdk1.utils.indexing import IndexingUtils
                from utils.file_storage.constants import FileStorageKeys

                from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
                    PromptIdeBaseTool,
                )

                summary_profile = ProfileManager.objects.get(
                    pk=summary_profile_id
                )
                fs_instance = EnvHelper.get_storage(
                    storage_type=StorageType.PERMANENT,
                    env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
                )
                util = PromptIdeBaseTool(
                    log_level=LogLevel.INFO, org_id=org_id
                )
                summarize_doc_id = IndexingUtils.generate_index_key(
                    vector_db=str(summary_profile.vector_store.id),
                    embedding=str(summary_profile.embedding_model.id),
                    x2text=str(summary_profile.x2text.id),
                    chunk_size="0",
                    chunk_overlap=str(summary_profile.chunk_overlap),
                    file_path=summarize_file_path,
                    fs=fs_instance,
                    tool=util,
                )
                PromptStudioIndexHelper.handle_index_manager(
                    document_id=document_id,
                    is_summary=True,
                    profile_manager=summary_profile,
                    doc_id=summarize_doc_id,
                )
            except ProfileManager.DoesNotExist:
                logger.warning(
                    "Summary profile %s not found", summary_profile_id
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
            _emit_error(
                log_events_id,
                executor_task_id,
                operation,
                error_msg,
                extra={
                    "prompt_ids": prompt_ids,
                    "document_id": document_id,
                    "profile_manager_id": profile_manager_id,
                },
            )
            return {"status": "failed", "error": error_msg}

        data = result_dict.get("data", {})

        # Sanitize outputs and metadata so that any non-JSON-safe
        # values (e.g. datetime from plugins) are converted before
        # they reach Django JSONField saves.
        outputs = _json_safe(data.get("output", {}))
        metadata = _json_safe(data.get("metadata", {}))

        # Re-fetch prompt ORM objects for OutputManagerHelper
        prompts = list(
            ToolStudioPrompt.objects.filter(prompt_id__in=prompt_ids).order_by(
                "sequence_number"
            )
        )

        response = OutputManagerHelper.handle_prompt_output_update(
            run_id=run_id,
            prompts=prompts,
            outputs=outputs,
            document_id=document_id,
            is_single_pass_extract=is_single_pass,
            profile_manager_id=profile_manager_id,
            metadata=metadata,
        )

        _emit_result(log_events_id, executor_task_id, operation, response)
        # Return minimal status — full data is sent via websocket above.
        # Returning the full response would cause Celery to log sensitive
        # extracted data in its "Task succeeded" message.
        return {"status": "completed", "operation": operation}
    except Exception as e:
        logger.exception("ide_prompt_complete callback failed")
        _emit_error(
            log_events_id,
            executor_task_id,
            operation,
            str(e),
            extra={
                "prompt_ids": prompt_ids,
                "document_id": document_id,
                "profile_manager_id": profile_manager_id,
            },
        )
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

        _emit_error(
            log_events_id,
            executor_task_id,
            operation,
            error_msg,
            extra={
                "prompt_ids": cb.get("prompt_ids", []),
                "document_id": cb.get("document_id", ""),
                "profile_manager_id": cb.get("profile_manager_id"),
            },
        )
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
        # Return minimal status to avoid logging sensitive extracted data
        return {"status": "completed", "operation": "fetch_response"}
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
        _emit_result(log_events_id, self.request.id, "single_pass_extraction", response)
        # Return minimal status to avoid logging sensitive extracted data
        return {"status": "completed", "operation": "single_pass_extraction"}
    except Exception as e:
        logger.exception("run_single_pass_extraction failed")
        _emit_error(log_events_id, self.request.id, "single_pass_extraction", str(e))
        raise
    finally:
        _clear_state_store()
