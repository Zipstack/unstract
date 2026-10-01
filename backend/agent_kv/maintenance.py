"""Agent-KV platform-wide maintenance logic (spec §5.4).

Two independent, idempotent, batch-capped jobs -- the never-dispatched/
stuck-job sweep and the TTL cleanup of expired staged files -- live here so
there is exactly one implementation shared by both invocation paths:

* the internal HTTP endpoints (``agent_kv/internal_views.py::SweepView``/
  ``TTLCleanupView``, ``POST /internal/v1/agent-kv/sweep/`` and
  ``.../ttl-cleanup/``), driven by the OSS/self-hosted PG-scheduler periodic
  task mechanism (``workers/scheduler/agent_kv_tasks.py``); and
* the ``agent_kv_sweep``/``agent_kv_ttl_cleanup`` Django management commands
  (``agent_kv/management/commands/``), driven by a Kubernetes CronJob in the
  cloud deployment.

Both callers get the identical dict shape back (``{"swept": N, "timed_out":
M}`` / ``{"cleaned": N}``), and both entrypoints are equally safe to call
more often than needed, or concurrently with each other -- everything below
is either a guarded UPDATE (``AgentKVJob.mark_terminal``) or a targeted
single-row write, never a queryset-wide one.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter
from agent_kv.storage import delete_job_files

_MAINTENANCE_BATCH_LIMIT = 500
_NEVER_DISPATCHED_ERROR = "Job was never dispatched"
_STUCK_JOB_ERROR = "Job timed out"


def run_sweep() -> dict:
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

    Platform-wide by design (no ``org_id`` parameter) -- invoked by a
    periodic maintenance mechanism (spec §5.4), not by something acting on
    one job/org.

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
    unbounded into memory or hold a caller open through a long loop.
    Idempotency (above) is what makes this safe to cap: whatever a call
    doesn't reach is still there, unchanged, for the next tick.
    """
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

    stuck_cutoff = now - timedelta(seconds=settings.AGENT_KV_STUCK_JOB_GRACE_SECONDS)
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

    return {"swept": swept, "timed_out": timed_out}


def run_ttl_cleanup() -> dict:
    """Delete staged files for expired jobs and blank their refs (spec §5.4).

    The job row itself is retained (audit trail) -- only the object-store
    paths are dropped, once nothing can read them any more (the status/
    result endpoints already 404 past ``expires_at`` -- Task 9). Blanking
    both refs after deletion is what makes a repeat call a no-op: the
    filter below only matches rows still carrying a non-blank ref, so a job
    already cleaned (or one that never staged an input/produced a result)
    drops out of the candidate set on the next pass.

    Platform-wide by design, same as :func:`run_sweep`.

    Batch-capped at ``_MAINTENANCE_BATCH_LIMIT`` (shared with
    :func:`run_sweep`) so one call can't stay open against a large expired
    backlog.

    Ordering is ``(cleanup_failed_at NULLS FIRST, expires_at)``, not
    ``expires_at`` alone. Retaining a ref whose delete failed is what makes a
    retry possible at all, but under a plain oldest-first ordering those same
    rows refill the batch every tick and nothing newer is ever reached: 500
    permanently-failing rows would stall cleanup completely, and every later
    expired job would keep its files past TTL. Sorting rows that have never
    failed ahead of rows that have bounds that -- a failure drifts behind all
    fresh work and is retried once the backlog is clear, and among failures the
    oldest failure goes first, so they rotate rather than one row monopolising
    the retries.
    """
    candidates = (
        AgentKVJob.objects.filter(expires_at__lt=timezone.now())
        .filter(Q(input_ref__gt="") | Q(result_ref__gt=""))
        .order_by(F("cleanup_failed_at").asc(nulls_first=True), "expires_at")[
            :_MAINTENANCE_BATCH_LIMIT
        ]
    )

    cleaned = 0
    retained = 0
    for job in candidates:
        # Blank only the refs whose files are CONFIRMED gone. Targeted
        # single-row update (not a queryset-wide `.update()`) for the same
        # reason it always was: one job's refs must never be blanked off the
        # back of another job's delete.
        #
        # A ref left set is the retry handle -- this loop used to blank both
        # unconditionally, so a transient object-store failure orphaned the file
        # permanently (the candidate filter below only matches rows that still
        # carry a non-blank ref, so a blanked row can never be reconsidered).
        cleared = delete_job_files(job)
        fields: dict = dict.fromkeys(cleared, "")
        if len(cleared) == 2:
            cleaned += 1
            # Fully cleaned rows drop out of the candidate filter anyway (both
            # refs blank), so this only matters for a row that failed before and
            # succeeded now -- it must not keep a stale failure marker.
            fields["cleanup_failed_at"] = None
        else:
            retained += 1
            # Stamped on every failed attempt, not just the first: the
            # nulls-first ordering uses this to push the row behind all fresh
            # work, and refreshing it rotates the retry order among failures
            # instead of letting the earliest-stamped row be retried forever.
            fields["cleanup_failed_at"] = timezone.now()
        AgentKVJob.objects.filter(id=job.id).update(**fields)
    # `retained` is reported, not just logged: these rows keep their refs and
    # are retried on a later tick (behind all never-failed work, per the
    # ordering above). A `retained` that stays high across ticks is the signal
    # that something is wrong with the object store rather than with one job --
    # the ordering stops it blocking progress, it does not make it harmless.
    return {"cleaned": cleaned, "retained": retained}
