"""Internal APIs for the agent-kv cloud executor (spec §5.4).

Mounted under ``/internal/v1/agent-kv/`` and guarded ambiently by
``InternalAPIAuthMiddleware`` -- these views take empty auth/permission
classes. Most require ``org_id`` in the body of every request (they act on
one job belonging to one org); the two maintenance views, ``SweepView`` and
``TTLCleanupView``, are the exception -- they are platform-wide and take no
``org_id`` at all, since they sweep across every org in one call.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import F, JSONField, Q, Value
from django.db.models.expressions import CombinedExpression
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter
from agent_kv.storage import (
    delete_input,
    delete_job_files,
    delete_result_file,
    write_result,
)

logger = logging.getLogger(__name__)

_VALID_STAGE_STATUSES = frozenset({"running", "done"})
_RESERVED_STAGE_ENTRY_KEYS = frozenset({"status", "seconds"})
_SCALAR_COUNTER_TYPES = (str, int, float, bool)
_MAINTENANCE_BATCH_LIMIT = 500
_NEVER_DISPATCHED_ERROR = "Job was never dispatched"
_STUCK_JOB_ERROR = "Job timed out"


def _sanitize_counters(counters) -> dict:
    """Keep only scalar counters that can't clobber the reserved fields.

    Task-11-review ruling: ``counters`` is untrusted executor payload --
    a key of ``status``/``seconds`` must not be able to override the
    endpoint's own reserved fields, and a nested dict/list value must not
    be admitted into the persisted stage entry (only scalars are).
    """
    if not isinstance(counters, dict):
        return {}
    return {
        key: value
        for key, value in counters.items()
        if key not in _RESERVED_STAGE_ENTRY_KEYS
        and isinstance(value, _SCALAR_COUNTER_TYPES)
    }


def _stage_merge_expression(stage: str, entry: dict) -> CombinedExpression:
    """Build a DB-side jsonb merge expression for one stage's entry.

    Compiles (on Postgres) to ``"stages" || %s``, the jsonb ``||``
    concatenation operator, which does a shallow top-level merge: only the
    ``stage`` key in the JSON column is touched, every other key is left
    exactly as the current row has it. This is what makes the merge safe
    against two concurrent stage reports for two *different* stages racing
    each other -- a Python-side ``dict(job.stages or {})`` read, merge, and
    full-column ``.update(stages=...)`` would let whichever write lands
    second silently clobber the first (task-11-review ruling).
    """
    return CombinedExpression(
        F("stages"),
        "||",
        Value({stage: entry}, output_field=JSONField()),
        output_field=JSONField(),
    )


class StageReportView(APIView):
    """Merge one stage's progress into ``job.stages`` (spec §5.4).

    This endpoint is the sole write gate for ``job.stages``: only the
    defined shape (``status``, optional ``seconds``, plus sanitized flat
    ``counters``) is ever persisted -- unexpected top-level body keys, and
    any counter that collides with a reserved key or isn't a scalar, are
    dropped rather than stored, so a later status-endpoint spread of a
    stage entry can't leak arbitrary payload content (task-9 review).
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)
        stage = body.get("stage")
        if not stage:
            return Response({"detail": "stage is required"}, status=400)
        status_value = body.get("status")
        if status_value not in _VALID_STAGE_STATUSES:
            return Response({"detail": "status must be 'running' or 'done'"}, status=400)

        job_qs = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).exclude(
            status__in=list(AgentKVJob.TERMINAL)
        )
        job = job_qs.first()
        if job is None:
            # Late report for a job that already reached a terminal state
            # (completed/failed/cancelled) -- a no-op, not an error.
            return Response({"ok": True, "noop": True})

        entry = {"status": status_value}
        if "seconds" in body:
            entry["seconds"] = body["seconds"]
        entry.update(_sanitize_counters(body.get("counters")))

        updates = {
            "stages": _stage_merge_expression(stage, entry),
            "stage": stage,
        }
        if job.status in (JobStatus.PENDING, JobStatus.DISPATCHED):
            updates["status"] = JobStatus.RUNNING
        # Re-guarded at update time: job_qs still excludes TERMINAL, so if
        # the job raced to terminal between the read above and this
        # UPDATE's WHERE clause, this becomes a silent no-op too.
        job_qs.update(**updates)
        return Response({"ok": True})


class FinalizeView(APIView):
    """Terminalize a job: write its result (on success) then mark it done.

    Idempotent: a job already in a terminal state short-circuits before any
    write -- ``write_result`` is only ever called for a job that is still
    non-terminal at read time, so a duplicate/late finalize call can never
    rewrite an already-written result. The concurrency slot is always
    released, in a ``finally``, on every path that actually attempts to
    finalize (success, duplicate no-op, or an exception raised while
    finalizing) -- but never on a 400 for a malformed body, since nothing
    was finalized (and therefore nothing had a slot to release yet).

    On the success path, ``write_result`` unavoidably runs *before* the
    ``mark_terminal`` guard (the result has to exist to get a ``result_ref``
    to pass into it) -- so a guard-loss right after the write (a concurrent
    cancel/duplicate finalize won instead) leaves a result file on disk with
    no ref anywhere pointing at it. That orphan is cleaned up immediately via
    ``storage.delete_result_file`` rather than left to leak past even TTL
    cleanup (which only ever acts on a job's *stored* ``result_ref``).

    Also deletes the staged input the moment ``mark_terminal`` actually
    wins (spec D10: "uploaded document deleted on job completion") -- the
    run is over either way, whether it completed or failed, so the input is
    no longer needed; the result file this same request may have just
    *successfully* written (guard won) is left completely untouched. Never
    runs on the duplicate/guard-lost path, since either another writer
    already owns cleanup or there's nothing new to terminalize.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)
        success = body.get("success")
        if not isinstance(success, bool):
            # Strict bool check (not truthy/falsy): a malformed/missing
            # `success` must 400 rather than silently fall through to the
            # failure branch and persist a FAILED job with an empty error.
            return Response({"detail": "success must be a boolean"}, status=400)

        job = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).first()
        finalized = False
        try:
            if job is not None and job.status not in AgentKVJob.TERMINAL:
                if success:
                    result_ref = write_result(
                        org_id, str(job_id), body.get("result") or {}
                    )
                    finalized = AgentKVJob.mark_terminal(
                        job_id,
                        org_id,
                        JobStatus.COMPLETED,
                        result_ref=result_ref,
                        usage_summary=body.get("usage_summary"),
                    )
                    if finalized:
                        job.status = JobStatus.COMPLETED
                    else:
                        # Guard lost after the write above (e.g. a cancel
                        # raced in between the read and mark_terminal's
                        # guarded UPDATE): the result we just wrote has no
                        # ref anywhere -- unreachable forever unless cleaned
                        # up here. Best-effort; never blocks the response.
                        delete_result_file(result_ref)
                else:
                    finalized = AgentKVJob.mark_terminal(
                        job_id,
                        org_id,
                        JobStatus.FAILED,
                        error=body.get("error") or "",
                    )
                    if finalized:
                        job.status = JobStatus.FAILED

                if finalized:
                    # A CANCELLED job never reaches here: cancel goes
                    # through JobCancelView/mark_terminal directly, not
                    # this finalize path, and a late finalize call against
                    # an already-CANCELLED job loses the terminal guard
                    # above -- so a cancelled job's input intentionally
                    # rides the normal TTL sweep instead of being deleted
                    # here.
                    delete_input(job)
                    AgentKVJob.objects.filter(id=job_id, organization_id=org_id).update(
                        input_ref=""
                    )
        finally:
            AgentKVConcurrencyLimiter.release(org_id, str(job_id))

        return Response(
            {
                "finalized": finalized,
                "webhook_url": job.webhook_url if job else "",
                "status": job.status.lower() if job else "",
            }
        )


class SweepView(APIView):
    """Terminalize PENDING-never-dispatched AND stuck jobs (spec §5.4).

    Two independent phases, run every call, each capped and counted
    separately:

    **Phase 1 -- never dispatched.** Mirrors ``workflow_manager``'s
    undispatched-execution sweep: the submit endpoint commits a PENDING row
    before dispatch runs, and an abort in between (client disconnect, worker
    crash, pod eviction) can leave it stranded with no owner -- ``PENDING``
    is not a terminal state, and nothing else recovers a job that was never
    queued. ``dispatched_at`` is stamped as a positive fact at dispatch
    time, so PENDING + older than the grace + ``dispatched_at IS NULL``
    means the dispatch never happened.

    **Phase 2 -- stuck in flight.** A job that *did* dispatch can still
    never terminalize: the executor pod can be killed, its callback queue
    can be lost, or the cloud engine itself can hang -- none of which
    ``mark_terminal`` ever sees, so a DISPATCHED/RUNNING row can sit
    forever holding a concurrency slot with no path back to terminal.
    ``dispatched_at`` (stamped positively at dispatch, spec §5.3/Fix 1) older
    than ``AGENT_KV_STUCK_JOB_GRACE_SECONDS`` is the only signal available --
    there is no heartbeat -- so this phase force-fails anything past that
    grace, same as the workflow reaper's stuck-execution recovery.

    Platform-wide by design (no ``org_id`` in the body, unlike every other
    view in this module) -- it is invoked by a periodic maintenance
    mechanism (spec §5.4), not the cloud executor acting on one job/org.

    Idempotent: ``mark_terminal``'s guarded UPDATE only terminalizes a row
    still in a non-terminal state, so a job already swept (or one that
    legitimately dispatched/finalized/was cancelled since the candidate
    query ran) is left alone by a repeat call. ``swept``/``timed_out`` each
    count guard successes, not candidates, so a race against a concurrent
    finalize/cancel/duplicate sweep is reflected accurately instead of
    double-counted.

    Each phase is independently batch-capped at ``_MAINTENANCE_BATCH_LIMIT``
    (oldest-first by its own ordering key) so a large backlog in either
    phase -- exactly what a dispatch-path or executor-fleet infra incident
    produces, which is also when this sweep matters most -- can't load
    unbounded into memory or hold this request open through a long loop.
    Idempotency (above) is what makes this safe to cap: whatever a call
    doesn't reach is still there, unchanged, for the scheduler's next tick.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        now = timezone.now()

        never_dispatched_cutoff = now - timedelta(
            seconds=settings.AGENT_KV_SWEEP_GRACE_SECONDS
        )
        never_dispatched_candidates = AgentKVJob.objects.filter(
            status=JobStatus.PENDING,
            created_at__lt=never_dispatched_cutoff,
            dispatched_at__isnull=True,
        ).order_by("created_at")[:_MAINTENANCE_BATCH_LIMIT]

        swept = 0
        for job in never_dispatched_candidates:
            # Per-job isolation is structural, not a try/except here:
            # mark_terminal is a guarded UPDATE that can't raise on a
            # normal outcome, and release() has its own internal
            # try/except (rate_limiter.py) -- so one job's failure can't
            # abort the loop for the rest of the batch.
            org_id = job.organization_id
            won = AgentKVJob.mark_terminal(
                job.id,
                org_id,
                JobStatus.FAILED,
                error=_NEVER_DISPATCHED_ERROR,
            )
            if won:
                swept += 1
                # Only a job this call actually terminalized held a slot
                # worth releasing here -- one a concurrent finalize/cancel
                # won instead already released its own slot on that path.
                AgentKVConcurrencyLimiter.release(str(org_id), str(job.id))

        stuck_cutoff = now - timedelta(
            seconds=settings.AGENT_KV_STUCK_JOB_GRACE_SECONDS
        )
        stuck_candidates = AgentKVJob.objects.filter(
            status__in=[JobStatus.DISPATCHED, JobStatus.RUNNING],
            dispatched_at__lt=stuck_cutoff,
        ).order_by("dispatched_at")[:_MAINTENANCE_BATCH_LIMIT]

        timed_out = 0
        for job in stuck_candidates:
            org_id = job.organization_id
            won = AgentKVJob.mark_terminal(
                job.id,
                org_id,
                JobStatus.FAILED,
                error=_STUCK_JOB_ERROR,
            )
            if won:
                timed_out += 1
                AgentKVConcurrencyLimiter.release(str(org_id), str(job.id))

        return Response({"swept": swept, "timed_out": timed_out})


class TTLCleanupView(APIView):
    """Delete staged files for expired jobs and blank their refs (spec §5.4).

    The job row itself is retained (audit trail) -- only the object-store
    paths are dropped, once nothing can read them any more (the status/
    result endpoints already 404 past ``expires_at`` -- Task 9). Blanking
    both refs after deletion is what makes a repeat call a no-op: the
    filter below only matches rows still carrying a non-blank ref, so a job
    already cleaned (or one that never staged an input/produced a result)
    drops out of the candidate set on the next pass.

    Platform-wide by design, same as :class:`SweepView`.

    Batch-capped at ``_MAINTENANCE_BATCH_LIMIT`` (shared with
    :class:`SweepView`) so one call can't hold a long-running request open
    against a large expired backlog; ordered by ``expires_at`` (indexed on
    this model) so the most-overdue rows drain first and the rest are left
    for the next call rather than starving behind an arbitrary slice.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        candidates = (
            AgentKVJob.objects.filter(expires_at__lt=timezone.now())
            .filter(Q(input_ref__gt="") | Q(result_ref__gt=""))
            .order_by("expires_at")[:_MAINTENANCE_BATCH_LIMIT]
        )

        cleaned = 0
        for job in candidates:
            delete_job_files(job)
            # Targeted single-row update (not a queryset-wide `.update()`):
            # each job's refs must be blanked only after ITS OWN files are
            # deleted, so a delete_job_files failure for one job can't blank
            # another job's still-undeleted refs.
            AgentKVJob.objects.filter(id=job.id).update(input_ref="", result_ref="")
            cleaned += 1
        return Response({"cleaned": cleaned})
