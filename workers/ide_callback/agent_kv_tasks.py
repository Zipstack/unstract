"""Agent-KV terminal callbacks (spec §5.3). Thin: parse, finalize, webhook.

These are the Celery ``link``/``link_error`` callbacks that
``agent_kv.dispatch.dispatch_job`` (backend, Task 8) attaches to the
executor dispatch: ``agent_kv_complete`` on success, ``agent_kv_error`` on
an unhandled executor exception. Both run on the dedicated
``agent_kv_callback`` queue (see
``shared/infrastructure/config/registry.py``) served by the IDE_CALLBACK
worker, and both terminalize the job via
``InternalAPIClient.agent_kv_finalize`` (Task 11's internal endpoint)
before firing the completion webhook (Task 13).
"""

import logging
from typing import Any

from queue_backend import worker_task
from shared.utils.webhook_notify import send_webhook

logger = logging.getLogger(__name__)

_UNKNOWN = "Executor failed without an error message"


def _get_api_client():
    """Lazily build an InternalAPIClient.

    Lazy import + plain instantiation (no shared config/session): mirrors
    ``queue_backend/pg_queue/consumer.py`` and ``.../reaper.py``'s
    ``_get_api_client`` helpers, which use this exact pattern to keep the
    module import-cycle-free at load time. Unlike ``ide_callback.tasks``'s
    ``_get_api_client`` (which returns a ``PromptStudioAPIClient`` scoped to
    a handful of prompt-studio endpoints), this callback talks to a general
    internal endpoint, so it goes through the general-purpose
    ``InternalAPIClient`` facade that owns ``agent_kv_finalize``.
    """
    from shared.api import InternalAPIClient

    return InternalAPIClient()


def _resolve_error(failed_task_id: str) -> str:
    """Look up the failed task's real exception via the Celery result backend.

    Mirrors ``ide_callback.tasks._get_task_error``'s ``AsyncResult`` lookup:
    the ``agent_kv_error`` link_error callback only ever receives the failed
    task's ID (see ``ExecutionDispatcher.dispatch_with_callback``'s
    docstring: "Receives (failed_task_uuid,) as first positional arg"), never
    the exception itself, so the real message has to be fetched from the
    result backend. Falls back to ``_UNKNOWN`` if the backend has no result
    (e.g. an eager/self-chained run) or the lookup itself errors.
    """
    try:
        from celery import current_app as app
        from celery.result import AsyncResult

        res = AsyncResult(failed_task_id, app=app)
        if res.result:
            return str(res.result)
    except Exception:
        pass
    return _UNKNOWN


@worker_task(name="agent_kv_complete")
def agent_kv_complete(
    result_dict: dict[str, Any],
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery link callback after the agent-kv executor task returns.

    ``result_dict["success"]`` reflects the *executor's* own outcome: it can
    still be ``False`` here even though this is the success ``link`` (the
    executor caught its error and returned a structured failure instead of
    raising, which would have routed to ``agent_kv_error`` instead). Either
    way the job is finalized via the internal API, then the webhook fires
    if the response says to.
    """
    cb = callback_kwargs or {}
    job_id = cb.get("job_id", "")
    org_id = cb.get("org_id", "")
    api = _get_api_client()

    if not result_dict.get("success", False):
        error = result_dict.get("error") or _UNKNOWN
        logger.error(
            "agent_kv executor reported failure: job_id=%s error=%s", job_id, error
        )
        out = api.agent_kv_finalize(job_id, org_id, success=False, error=error)
    else:
        data = result_dict.get("data") or {}
        out = api.agent_kv_finalize(
            job_id,
            org_id,
            success=True,
            result=data.get("output") or {},
            usage_summary=data.get("usage_summary"),
        )

    _maybe_webhook(out, job_id)
    return {"job_id": job_id, "finalized": out.get("finalized", False)}


@worker_task(name="agent_kv_error")
def agent_kv_error(
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Celery link_error callback when the agent-kv executor task raises."""
    cb = callback_kwargs or {}
    job_id = cb.get("job_id", "")
    org_id = cb.get("org_id", "")
    api = _get_api_client()

    error = _resolve_error(failed_task_id)
    logger.error("agent_kv executor task failed: job_id=%s error=%s", job_id, error)
    out = api.agent_kv_finalize(job_id, org_id, success=False, error=error)

    _maybe_webhook(out, job_id)
    return {"job_id": job_id, "finalized": out.get("finalized", False)}


def _maybe_webhook(finalize_response: dict[str, Any], job_id: str) -> None:
    """Fire the completion webhook, but only for a fresh finalize.

    ``finalized`` is ``False`` for a duplicate/late finalize call (the job
    was already terminal) as well as for an unknown job -- either way the
    webhook already fired (or never should), so firing again here would
    double-notify the caller.
    """
    if not finalize_response.get("finalized"):
        return
    url = finalize_response.get("webhook_url") or ""
    if not url:
        return
    send_webhook(url, {"job_id": job_id, "status": finalize_response.get("status", "")})
