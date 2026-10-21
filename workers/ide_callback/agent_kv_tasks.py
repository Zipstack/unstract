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
import os
from typing import Any

from queue_backend import worker_task
from shared.utils.webhook_notify import send_webhook

from unstract.core.network.ssrf import (
    is_retryable_refusal,
    webhook_url_refusal,
)

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


def _resolve_error(failed_task_id: str, explicit: str | None = None) -> str:
    """Resolve the real error text for the ``agent_kv_error`` link_error callback.

    Mirrors ``ide_callback.tasks._get_task_error``'s precedence exactly:
    prefer ``explicit`` when the caller already has it. The PG-queue
    transport's self-chained error path (``queue_backend/pg_queue/consumer.py``'s
    ``_chain_continuation``) hands the real exception through
    ``callback_kwargs["error"]`` -- on that path the executor ran eagerly and
    never wrote a Celery result backend entry under ``failed_task_id``, so
    the ``AsyncResult`` lookup below would come back empty. The Celery
    ``link_error`` path (``agent_kv.dispatch.dispatch_job``) passes no
    explicit error and relies on the result backend, then ``_UNKNOWN``.

    Falsy-aware (``explicit or ...``), matching ``_get_task_error``'s own
    ``if explicit is not None`` intent in practice: an empty-string
    ``explicit`` (e.g. an executor that raised with no message) must not be
    persisted verbatim as a blank error -- it falls through to the result
    backend lookup, then ``_UNKNOWN``, same as an absent explicit error.

    Kept as a sibling implementation rather than importing
    ``ide_callback.tasks._get_task_error`` directly: ``ide_callback/tasks.py``
    already imports *this* module at its own bottom (so both of
    ``workers/worker.py``'s task-loading mechanisms register
    ``agent_kv_complete``/``agent_kv_error`` -- see that file's comment).
    Importing back from ``tasks.py`` here would still resolve (Python
    tolerates the resulting redundant re-import under the two different
    ``sys.modules`` names that mechanism ends up using), but it adds a
    two-way coupling between the modules for ~10 lines of small, stable
    logic that isn't worth the added complexity to reason about.
    """
    if explicit:
        return explicit
    try:
        from celery import current_app as app
        from celery.result import AsyncResult

        res = AsyncResult(failed_task_id, app=app)
        if res.result:
            return str(res.result)
    except Exception:
        # Was a bare `pass`. The common case here is a kombu deserialization
        # failure: the executor raised a cloud-plugin exception class that is
        # not importable in the OSS ide_callback image, so the result backend
        # has the error and this process cannot read it. The job is then
        # finalized with "Executor failed without an error message" -- the exact
        # useless error this lookup exists to avoid -- and silently, so the real
        # cause was unrecoverable even from logs.
        logger.warning(
            "Could not read the executor error from the result backend for "
            "task %s; the job will be finalized with a generic message",
            failed_task_id,
            exc_info=True,
        )
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

    try:
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

    except Exception:
        logger.exception(
            "agent_kv_complete callback failed: job_id=%s org_id=%s", job_id, org_id
        )
        raise


@worker_task(
    bind=True,
    name="agent_kv_error",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def agent_kv_error(
    self,
    failed_task_id: str,
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Celery link_error callback when the agent-kv executor task raises.

    This is the SOLE terminalizer of a failed job, so a finalize that does not
    happen is a job stuck in RUNNING. It used to catch, log and ``return None``
    -- which the consumer records as SUCCESS, deletes the message, and moves on:
    no retry, no dead letter, no failed-task record. A momentary backend blip
    during finalize therefore stranded the job until the sweep eventually
    terminalized it with "Job timed out", overwriting the real executor error,
    which existed only in the log line above.

    Now retries and RAISES on exhaustion, matching its sibling
    ``agent_kv_complete`` and the ``process_batch_callback_api`` precedent in
    ``workers/callback/tasks.py``. The PG consumer relies on task-level
    autoretry for exactly this (see its own comment in
    ``queue_backend/pg_queue/consumer.py``).

    **What ``retry_backoff`` actually does here: nothing.** The PG consumer runs
    tasks via ``task.apply(..., throw=True)``
    (``queue_backend/pg_queue/consumer.py``) -- i.e. EAGER. Celery's eager
    retry recurses synchronously and ignores ``countdown``, so
    ``retry_backoff=True`` / ``retry_backoff_max=300`` / ``retry_jitter=True``
    produce three back-to-back attempts in microseconds, which rides out no
    "momentary blip" at all. They are kept because they are correct for the
    Celery transport and cost nothing under the PG one -- not because they
    space the attempts out here.

    The delay that genuinely helps comes AFTER exhaustion, from vt-redelivery
    once this raises and the message's visibility timeout lapses. So the value
    of the raise is not just the failed-task record: it is the only thing that
    buys any real elapsed time before the next attempt. An earlier version of
    this docstring credited the decorator with that, which would mislead anyone
    tuning the backoff to fix a slow finalize.

    ``autoretry_for=(Exception,)`` rather than a narrow transport type: the
    whole point is that this task must not quietly give up, and a programming
    error that burns three retries and then surfaces loudly is a far better
    outcome than one that returns None and reports success.
    """
    cb = callback_kwargs or {}
    job_id = cb.get("job_id", "")
    org_id = cb.get("org_id", "")
    api = _get_api_client()

    try:
        error = _resolve_error(failed_task_id, explicit=cb.get("error"))
        logger.error("agent_kv executor task failed: job_id=%s error=%s", job_id, error)
        out = api.agent_kv_finalize(job_id, org_id, success=False, error=error)

        _maybe_webhook(out, job_id)
        return {"job_id": job_id, "finalized": out.get("finalized", False)}

    except Exception:
        logger.exception(
            "agent_kv_error callback failed: job_id=%s org_id=%s (retry %s of %s)",
            job_id,
            org_id,
            self.request.retries,
            self.max_retries,
        )
        raise


def _deliver_terminal_webhook(task, callback_kwargs, default_status: str) -> dict | None:
    """Deliver one terminal webhook, with the retry policy both tasks share.

    Extracted so `agent_kv_cancelled` and `agent_kv_finalized` cannot drift:
    they differ only in which terminal state they announce, and the hard part
    -- telling a retryable failure from a permanently undeliverable URL -- is
    identical and worth having in one place.
    """
    cb = callback_kwargs or {}
    job_id = cb.get("job_id", "")
    url = cb.get("webhook_url", "")
    # The backend sends the status it actually terminalized the row to, so a
    # finalize announces `completed` or `failed` from the row itself rather
    # than this worker guessing. `default_status` covers an enqueue from an
    # older producer that did not send one.
    status = cb.get("status") or default_status
    if not url:
        return None
    try:
        delivered = _send_webhook(url, job_id, status)
    except Exception:
        logger.exception(
            "agent_kv terminal webhook failed: job_id=%s status=%s", job_id, status
        )
        raise
    if not delivered:
        # `send_webhook` returns False for THREE different things: a non-2xx
        # response, a connection failure, and a URL its SSRF guard refuses.
        # Only the first two are worth retrying.
        #
        # Retrying a refused URL cannot ever succeed -- the reason is a
        # property of the URL, not of the network -- so it burned the full
        # retry budget (~20 attempts) and ended in a poison drop, for a
        # caller who simply gave an `http://` or private-host webhook. Submit
        # now refuses those up front, but a key created before that, or a
        # resolver that starts answering differently, can still reach here.
        reason = webhook_url_refusal(url, allowed_schemes=("https",))
        if reason is not None and not is_retryable_refusal(reason):
            # Logged at ERROR, not swallowed quietly: the caller still did not
            # get their notification, and that is worth seeing. But the queue
            # message is acknowledged, because nothing about repeating this
            # will change the outcome.
            logger.error(
                "agent-kv: webhook_url for job %s is permanently undeliverable "
                "(%s); not retrying",
                job_id,
                reason,
            )
            return {"job_id": job_id, "status": status, "webhook_skipped": reason}
        logger.error(
            "agent-kv: %s webhook not delivered for job %s (retry %s of %s)",
            status,
            job_id,
            task.request.retries,
            task.max_retries,
        )
        raise RuntimeError(f"{status} webhook not delivered for job {job_id}")
    return {"job_id": job_id, "status": status}


@worker_task(
    bind=True,
    name="agent_kv_cancelled",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def agent_kv_cancelled(
    self,
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fire the terminal webhook for a job cancelled by the API.

    Cancellation does not go through finalize: ``JobCancelView`` (and DELETE
    on a non-terminal job) terminalizes the row directly, releases the slot
    and returns. So nothing in the finalize path ever fired a webhook for it,
    and a late executor callback cannot either -- it loses the terminal guard
    and ``_maybe_webhook`` correctly declines a non-fresh finalize. The caller
    who supplied ``webhook_url`` was simply never told, despite docs §8
    promising delivery on terminal states.

    Enqueued by the backend ONLY when its guarded cancel actually won, which
    is what keeps this from double-notifying: if the cancel lost to a
    finalize, the backend does not enqueue and ``agent_kv_finalized`` is
    queued instead. Exactly one of the two paths owns the notification for any
    given job.
    """
    return _deliver_terminal_webhook(self, callback_kwargs, "cancelled")


@worker_task(
    bind=True,
    name="agent_kv_finalized",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def agent_kv_finalized(
    self,
    callback_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fire the terminal webhook for a job that finalize just terminalized.

    The counterpart to ``agent_kv_cancelled``, and enqueued the same way: by
    the backend, from the request whose ``mark_terminal`` actually won. The
    two are mutually exclusive, so a job gets exactly one terminal
    notification.

    This used to be sent inline by ``_maybe_webhook`` right after the finalize
    call returned. That lost the notification whenever the finalize RESPONSE
    was lost: the worker retried, the replay found an already-terminal row and
    reported ``finalized: False``, and the worker declined to send -- correctly,
    because out here a non-fresh finalize is indistinguishable from the
    ordinary duplicate-callback case where the webhook already went out.
    Queuing it from the backend instead ties the notification to the guard
    rather than to the survival of an HTTP response.
    """
    return _deliver_terminal_webhook(self, callback_kwargs, "completed")


def _send_webhook(
    url: str, job_id: str, status: str, *, result_available: bool = False
) -> bool:
    """Deliver one terminal notification.

    Single place the SSRF waiver is read, so the cancel path cannot drift from
    the finalize path on what it permits.

    ``result_available`` adds one key to the otherwise fixed ``{job_id,
    status}`` payload, and is set on exactly one notification: the follow-up for
    a job cancelled after its extraction had already finished, whose result is
    therefore readable even though the status is ``cancelled``. It is additive
    -- a receiver that ignores unknown keys sees a repeat of the cancellation it
    already got -- and it is the only thing that distinguishes the follow-up
    from that first notification, which is why it is sent rather than a bare
    duplicate: an identical second POST would carry no information at all.
    """
    # Test/dev stacks only (e2e lane): waive the SSRF guards so a receiver on
    # the compose host is reachable. Unset/false in production.
    allow_insecure = os.environ.get(
        "AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE", ""
    ).lower() in ("1", "true", "yes")
    payload: dict[str, Any] = {"job_id": job_id, "status": status}
    if result_available:
        payload["result_available"] = True
    return send_webhook(url, payload, allow_insecure=allow_insecure)


def _maybe_webhook(finalize_response: dict[str, Any], job_id: str) -> None:
    """Send whichever notifications the BACKEND did not take ownership of.

    Normally that is just one: the `result_available` follow-up. The terminal
    notification is queued by the backend (`agent_kv_finalized`) from the
    request whose `mark_terminal` won, exactly as it has always been for
    cancellation (`agent_kv_cancelled`).

    It used to be sent from here, which tied it to the finalize RESPONSE
    surviving: lose that response and this worker retried, the replay reported
    `finalized: False`, and the send was skipped -- correctly, because from out
    here a non-fresh finalize is indistinguishable from the ordinary duplicate
    whose webhook already went out. The caller was never told and nothing
    recorded the miss.

    **The inline send is kept as a fallback, gated on the backend saying it
    did NOT queue one.** Which side owns delivery is now stated in the
    response rather than assumed: a worker that stopped sending inline,
    talking to a backend that does not yet enqueue, would drop the
    notification entirely -- neither side sends, and the callback is
    acknowledged. `webhook_enqueued` absent or False means delivery is still
    this worker's, which is exactly how an older backend's response reads, so
    no version check is needed.

    Transitional, and worth deleting: once no backend predating
    `webhook_enqueued` can be running, this branch and the field go together.
    The fallback carries the original defect by construction -- it is the old
    code path -- but a notification that can be lost on a replay beats one
    that is never sent at all.
    """
    url = finalize_response.get("webhook_url") or ""
    if not url:
        return

    if finalize_response.get("finalized"):
        if finalize_response.get("webhook_enqueued"):
            return
        logger.warning(
            "agent-kv: finalize for job %s did not queue a terminal webhook "
            "(backend predates `webhook_enqueued`); sending it inline. This "
            "delivery is lost if the finalize response does not survive",
            job_id,
        )
        status = finalize_response.get("status", "")
        if not _send_webhook(url, job_id, status):
            logger.error(
                "agent-kv webhook not delivered for job %s (status=%s); the "
                "caller was not notified and nothing will retry",
                job_id,
                status,
            )
        return

    # Not a terminal transition, so there is no guard for the backend to hang
    # it on: the job was CANCELLED after its extraction had already finished,
    # so the backend kept the paid-for result on the cancelled row. The
    # cancellation webhook went out when that cancel won and nothing follows
    # it -- a webhook-driven caller, with no reason to poll a job they were
    # told was cancelled, would never learn the answer is there to read.
    if finalize_response.get("result_attached"):
        _notify_result_available(url, job_id)


def _notify_result_available(url: str, job_id: str) -> None:
    """Follow up a cancellation notification that is now out of date.

    Sent only when ``FinalizeView`` reports ``result_attached``: the job was
    cancelled while its extraction was finishing, the usage was already flushed
    and billed, and the result is therefore kept and served by
    ``GET /agent-kv/{job_id}/result`` alongside ``status: "cancelled"``.

    Logged at ERROR rather than raised on failure, matching the fresh-finalize
    branch above and for the same reason: the job is already terminal and its
    result already stored, so raising would only re-run a finalize whose work is
    done. The result stays readable either way -- this notification is what
    saves the caller a poll, not what makes the answer available.
    """
    if not _send_webhook(url, job_id, "cancelled", result_available=True):
        logger.error(
            "agent-kv result-available follow-up not delivered for job %s; the "
            "caller was told `cancelled` and will not learn that the result was "
            "kept unless they poll the result endpoint",
            job_id,
        )
