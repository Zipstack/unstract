"""Executor dispatch glue (spec §5.3). One dispatch per job; UUID task_id."""

import logging
import uuid

from celery import signature
from django.conf import settings
from django.utils import timezone
from unstract.sdk1.execution.context import ExecutionContext

from agent_kv.constants import EXECUTION_SOURCE, EXTRACTOR_ROUTES
from agent_kv.models import AgentKVJob, JobStatus

logger = logging.getLogger(__name__)

CALLBACK_QUEUE = "agent_kv_callback"


class DispatchError(Exception):
    """Enqueue failed; the caller terminalizes the job (spec §5.3)."""


def _enqueue_webhook(task_name: str, job, status: str) -> bool:
    """Queue a terminal-webhook task for ``job``, best-effort.

    Shared by the cancel and finalize paths so the two cannot drift: both
    terminal notifications are OWNED BY THE BACKEND and queued by whichever
    request won the terminal guard. Delivery, retries and the permanently-
    undeliverable case are the worker's problem.

    Best-effort by design, as the cancel path has always been: the job is
    already terminal and the caller already has their response, so failing
    that request because a notification could not be QUEUED would be the
    wrong trade. Logs and returns.

    Returns whether a task was actually queued, which is NOT the same as
    "this job has a webhook". A queue that is down returns False, and
    finalize reports that to the callback worker as `webhook_enqueued:
    false` so the worker falls back to sending inline. Reporting True on a
    swallowed failure would mean neither side sends -- the exact loss this
    whole change exists to remove.
    """
    if not job.webhook_url:
        return False
    try:
        from pg_queue.producer import enqueue_task

        enqueue_task(
            task_name=task_name,
            queue=CALLBACK_QUEUE,
            kwargs={
                "callback_kwargs": {
                    "job_id": str(job.id),
                    "webhook_url": job.webhook_url,
                    "status": status,
                }
            },
            org_id=str(job.organization_id),
        )
    except Exception:
        logger.exception(
            "agent-kv: could not queue the %s webhook for job %s; the job IS "
            "%s, only the notification was lost",
            status,
            job.id,
            status,
        )
        return False
    return True


def dispatch_terminal_webhook(job, status: str) -> bool:
    """Queue the terminal webhook for a job finalize just terminalized.

    Call ONLY when ``mark_terminal`` actually won, which is what makes this
    mutually exclusive with ``dispatch_cancelled_webhook``: a finalize that
    won means no cancel did, and vice versa. Exactly one path notifies.

    **Why the backend owns this rather than the callback worker.** The worker
    used to send it inline after finalize returned. If that HTTP response was
    lost -- a timeout, or a 5xx -- the worker retried, the replay found an
    already-terminal row and reported ``finalized: False``, and the worker
    correctly declined to send, because from out there a non-fresh finalize is
    indistinguishable from the ordinary duplicate-callback case where the
    webhook already went out. The caller was never told and nothing recorded
    the miss. Queuing here instead means the notification is committed by the
    one request that won the guard, so losing the response to that request no
    longer loses the notification: the queued task has its own retry budget
    and a visible failure.

    The residual window is a process death between the guard-winning UPDATE
    and this enqueue, which is microseconds rather than a whole HTTP round
    trip. Closing that too would mean enqueuing inside ``mark_terminal``'s
    transaction; it is not done here because the enqueue is deliberately
    best-effort and must not be able to roll back a terminal state.

    Returns whether the task was queued, which finalize passes to the
    callback worker so it knows whether delivery is still its own.
    """
    return _enqueue_webhook("agent_kv_finalized", job, status)


def dispatch_cancelled_webhook(job) -> bool:
    """Queue the terminal webhook for a job the API just cancelled.

    Cancellation never reaches finalize -- ``JobCancelView`` and DELETE
    terminalize the row themselves -- so without this the caller who supplied
    ``webhook_url`` is never told, and a late executor callback cannot tell them
    either (it loses the terminal guard, and the callback declines a non-fresh
    finalize rather than double-notifying). Docs §8 promises delivery on
    terminal states; this is the cancel half of that promise.

    Call ONLY when the guarded cancel actually won. That is what makes the two
    paths mutually exclusive: a cancel that lost means a finalize won and will
    send, and a cancel that won means no fresh finalize can.

    One thing a late callback CAN now add, and it is additive to this rather
    than a competitor for it: if the cancelled job's extraction had already
    finished, its result is attached to the row and a ``result_available``
    follow-up is sent (``ide_callback.agent_kv_tasks._maybe_webhook``), because
    this notification has already told the caller the job was cancelled and
    nothing else would ever correct that. The TERMINAL notification is still
    this one, sent exactly once.

    Best-effort by design. The job is already cancelled and the caller already
    has their 200; failing their request because a notification could not be
    QUEUED would be the wrong trade, so this logs and returns rather than
    raising. Delivery itself is the worker's problem.
    """
    return _enqueue_webhook("agent_kv_cancelled", job, "cancelled")


def _dispatcher():
    # No `celery_app`: UN-4046 removed that parameter when the routing
    # dispatcher's Celery branch went with the pg_queue_enabled flag. Passing it
    # raises TypeError, so every submit failed to dispatch -- and because it
    # fails at the call rather than at import, nothing catches it until a real
    # request is made.
    from pg_queue.executor_rpc import get_executor_dispatcher

    return get_executor_dispatcher()


def _platform_api_key(job) -> str:
    # Lazy import: avoids Django app registry init order (mirrors
    # PromptStudioHelper._get_platform_api_key).
    from platform_settings_v2.platform_auth_service import (
        PlatformAuthenticationService,
    )

    # ``get_active_platform_key`` takes the org's public *slug*
    # (``Organization.organization_id``, e.g. ``org_abc123``) and resolves it
    # via ``get_organization_by_org_id`` -- NOT the row's UUID primary key that
    # ``job.organization_id`` holds. Passing the PK here silently resolves to
    # no organization and every dispatch fails with ``ActiveKeyNotFound``
    # (caught live in the Task 13b integration run).
    org_slug = job.organization.organization_id
    platform_key = PlatformAuthenticationService.get_active_platform_key(org_slug)
    if not platform_key:
        raise DispatchError(f"No active platform key for org {org_slug}")
    return str(platform_key.key)


def dispatch_job(
    job, *, extractor: str, schema: dict, options: dict, adapters: dict | None = None
) -> None:
    executor_name, operation = EXTRACTOR_ROUTES[extractor]
    org_id = str(job.organization_id)
    # Everything that can fail — platform-key lookup, context construction,
    # and the enqueue call itself — lives inside this try so no internal
    # failure (e.g. a transient DB error resolving the platform key) can
    # escape as a raw, uncaught exception. Only the post-success bookkeeping
    # below runs outside it.
    try:
        job.task_id = uuid.uuid4()
        context = ExecutionContext(
            executor_name=executor_name,
            operation=operation,
            run_id=str(job.id),
            execution_source=EXECUTION_SOURCE,
            organization_id=org_id,
            executor_params={
                "job_id": str(job.id),
                "input_ref": job.input_ref,
                "schema": schema,
                "options": options,
                # Platform adapter instance ids, by role, already validated at
                # submit against THIS job's organization and against the
                # expected `AdapterTypes` (see
                # `execution_serializers._validated_adapter_shape` for the
                # shape half and `execution_views._resolved_adapters` for the
                # tenancy half).
                #
                # Defence in depth, NOT the only check: the platform service
                # re-scopes every lookup as
                # `WHERE id=%s and organization_id=%s`
                # (platform-service/.../helper/adapter_instance.py:28-30),
                # where the org comes from the bearer platform key that
                # `_platform_api_key(job)` below mints from THIS job's org. So
                # org A cannot spend org B's credential even with the submit
                # gate removed. What the submit gate buys is a clean 400 naming
                # the role instead of a mid-run `SdkError`, plus the two checks
                # the platform service does NOT make: `is_usable` (exhausted
                # trial) and `is_available` (deprecated).
                #
                # Empty for an env-configured extractor (`kv`), which is why
                # this is a dict rather than three params: the two credential
                # models coexist, one per extractor.
                "adapters": adapters or {},
                "platform_api_key": _platform_api_key(job),
                # The CAP the engine must enforce (spec §6.1/§6.6), not the
                # measured count -- job.pages_total is None for Excel (no
                # pre-OCR page concept), which would otherwise leave the
                # engine with nothing to check the post-OCR virtual-page cap
                # against. The measured count still rides along separately.
                "max_pages": settings.AGENT_KV_MAX_PAGES,
                "pages_total": job.pages_total,
            },
        )
        # Last check before spending money. A cancel can land between the
        # submit's `job.save()` and this enqueue: the cancel sees a PENDING,
        # never-dispatched row, so it terminalizes it AND releases its
        # concurrency slot -- correctly, because nothing had been dispatched
        # yet. Enqueueing anyway would then run paid work for a job the caller
        # already cancelled, with its slot already handed to someone else.
        #
        # Re-read rather than trusting the in-memory row, which predates the
        # cancel by construction.
        if AgentKVJob.objects.filter(
            id=job.id, status__in=list(AgentKVJob.TERMINAL)
        ).exists():
            logger.info(
                "agent-kv: job %s was terminalized before dispatch; not enqueueing",
                job.id,
            )
            return

        cb_kwargs = {"callback_kwargs": {"job_id": str(job.id), "org_id": org_id}}
        _dispatcher().dispatch_with_callback(
            context,
            on_success=signature(
                "agent_kv_complete", kwargs=cb_kwargs, queue=CALLBACK_QUEUE
            ),
            on_error=signature("agent_kv_error", kwargs=cb_kwargs, queue=CALLBACK_QUEUE),
            task_id=str(job.task_id),
        )
    except DispatchError:
        raise
    except Exception as e:
        raise DispatchError(str(e)) from e
    job.status = JobStatus.DISPATCHED
    job.dispatched_at = timezone.now()
    # Guarded queryset UPDATE, not job.save(): a plain save would blindly
    # overwrite whatever status this job already raced to. Concretely: the
    # executor can fail (or the job be cancelled) essentially instantly
    # after enqueue, and its finalize callback can land -- marking the row
    # FAILED/CANCELLED -- before this post-enqueue bookkeeping runs. An
    # unconditional save() here would rewrite that terminal status back to
    # DISPATCHED, un-terminalizing the job forever (nothing else ever
    # revisits a DISPATCHED row). Only a still-PENDING row is advanced; a
    # row this UPDATE doesn't match is left exactly as the winning writer
    # left it. `modified_at` is stamped automatically by
    # BaseModelQuerySet.update() (utils/models/base_model.py).
    # Everything below is POST-ENQUEUE bookkeeping. The task is already on the
    # queue, so a failure here must never be reported as a failed dispatch:
    # `SubmitView` turns a DispatchError into a FAILED job, and the executor
    # would then run, callback, and find a terminal row it cannot write to --
    # the caller told nothing was billed for work that did run. Wrapped rather
    # than left to propagate, which is what the single pre-review UPDATE did.
    #
    # Losing the bookkeeping entirely is recoverable: sweep phase 1 reaps a
    # still-PENDING row with no `dispatched_at`, and phase 2's
    # `dispatched_at IS NULL` arm covers the non-PENDING case.
    try:
        _record_dispatch(job)
    except Exception:
        logger.exception(
            "agent-kv: dispatch bookkeeping failed for job %s after enqueue "
            "(task is queued; the sweep will reconcile)",
            job.id,
        )


def _record_dispatch(job) -> None:
    """Persist task_id/status/dispatched_at against whatever the row raced to."""
    advanced = AgentKVJob.objects.filter(id=job.id, status=JobStatus.PENDING).update(
        task_id=job.task_id,
        status=job.status,
        dispatched_at=job.dispatched_at,
    )
    if not advanced:
        # The row moved off PENDING between the enqueue above and this write.
        # The benign case is a terminal status (the guard's whole purpose) --
        # but there is a non-terminal one: StageReportView promotes
        # PENDING -> RUNNING on the executor's FIRST stage report, which can
        # easily land before this bookkeeping. The guard above then matches 0
        # rows and `dispatched_at` stays NULL -- and a non-terminal row with a
        # NULL `dispatched_at` is invisible to BOTH sweep phases: phase 1
        # requires `status=PENDING`, phase 2 filters `dispatched_at__lt=cutoff`
        # and SQL `NULL < x` is never true. The job reports `running` forever
        # and `GET result` 409s for the life of the row, with nothing able to
        # recover it.
        #
        # So stamp the dispatch bookkeeping for any still-non-terminal row,
        # WITHOUT touching `status`: the row genuinely was dispatched, and
        # moving RUNNING back to DISPATCHED would lose the executor's own
        # progress. `dispatched_at__isnull=True` keeps this idempotent and
        # stops a retry overwriting the original dispatch time.
        AgentKVJob.objects.filter(id=job.id, dispatched_at__isnull=True).exclude(
            status__in=list(AgentKVJob.TERMINAL)
        ).update(task_id=job.task_id, dispatched_at=job.dispatched_at)
