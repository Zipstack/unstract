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

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import SLOT_TTL_SECONDS, AgentKVConcurrencyLimiter
from agent_kv.storage import delete_job_files

logger = logging.getLogger(__name__)

_MAINTENANCE_BATCH_LIMIT = 500
# Slots in each TTL-cleanup batch held for rows whose file delete failed before.
# Caps the retry lane (so failures cannot crowd out new expirations) and
# guarantees it (so new expirations cannot crowd out retries) -- review found
# the implementation starving each side in turn when one ordering tried to do
# both. 20% leaves 400 slots for the normal case, where nothing is retrying.
_TTL_RETRY_RESERVE = 100
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
    # `dispatched_at__lt` OR `dispatched_at IS NULL`, not just the former.
    # A DISPATCHED/RUNNING row whose `dispatched_at` is NULL is unreachable by
    # a `__lt` filter alone -- SQL `NULL < x` is never true -- so such a row
    # would hang in a non-terminal state forever. dispatch.py now stamps
    # `dispatched_at` for any non-terminal row precisely so this cannot
    # normally happen; this arm is the backstop for the window that remains
    # (the worker dying between the enqueue and that stamp), because the cost
    # of missing one is a job that never terminalizes at all. Such a row falls
    # back to `created_at` for the age test, which is the only timestamp it
    # has.
    stuck_candidates = (
        AgentKVJob.objects.filter(
            status__in=[JobStatus.DISPATCHED, JobStatus.RUNNING],
        )
        .filter(
            Q(dispatched_at__lt=stuck_cutoff)
            | Q(dispatched_at__isnull=True, created_at__lt=stuck_cutoff)
        )
        # Coalesce, not a bare `dispatched_at`. The second Q arm exists to
        # recover rows whose post-enqueue bookkeeping was lost -- they have
        # `dispatched_at IS NULL` -- but Postgres sorts ascending NULLS LAST,
        # so with a full batch of non-NULL stuck rows ahead of them those rows
        # were never selected. The backstop could not fire in exactly the
        # situation it exists for: a backlog.
        .order_by(Coalesce("dispatched_at", "created_at"))[:_MAINTENANCE_BATCH_LIMIT]
    )

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

    # Phase 3: release slots still held by jobs that were CANCELLED after being
    # dispatched.
    #
    # Cancelling a dispatched job deliberately does NOT release its slot -- the
    # executor is still running and still billing, so the slot belongs to the
    # finalize callback that will arrive when it finishes. But if that executor
    # dies, no callback ever arrives, and neither phase above selects a
    # CANCELLED row: phase 1 wants PENDING, phase 2 wants DISPATCHED/RUNNING.
    # The slot then sits occupied until Redis expires it.
    #
    # Bounded on BOTH sides, which is what keeps this from rescanning the same
    # ancient rows forever: older than the stuck grace (so a live executor is
    # not cut short) and newer than the slot TTL (past which Redis has already
    # dropped the entry, so there is nothing left to release).
    slot_ttl_floor = now - timedelta(seconds=SLOT_TTL_SECONDS)
    abandoned_cancelled = AgentKVJob.objects.filter(
        status=JobStatus.CANCELLED,
        dispatched_at__isnull=False,
        completed_at__lt=stuck_cutoff,
        completed_at__gt=slot_ttl_floor,
        # NEWEST first, the opposite of the other two phases and deliberate.
        # Releasing a slot does not remove its row from this query -- there is
        # no "released" marker -- so oldest-first would re-select the same 500
        # rows every sweep whenever the backlog exceeds the batch limit, and
        # rows arriving behind them would age out of the window never having
        # been looked at.
        #
        # Newest-first inverts which rows lose: the ones skipped are the oldest,
        # i.e. closest to the slot TTL floor, where Redis is about to drop the
        # entry anyway and a release buys almost nothing. Every row is seen
        # while its release still matters, unless more than
        # `_MAINTENANCE_BATCH_LIMIT` become eligible inside one sweep interval
        # -- and the TTL remains the backstop for that.
    ).order_by("-completed_at")[:_MAINTENANCE_BATCH_LIMIT]

    released = 0
    for job in abandoned_cancelled:
        # `release` is an idempotent zrem, so re-releasing a slot the callback
        # already freed costs nothing and is not worth a guard.
        AgentKVConcurrencyLimiter.release(str(job.organization_id), str(job.id))
        released += 1
    if released:
        logger.info(
            "agent-kv sweep released %s concurrency slot(s) held by cancelled "
            "jobs whose executor never called back",
            released,
        )

    # These two counts are the only evidence the sweep ran and the only
    # evidence it had to do anything. A sweep that terminalizes a thousand jobs
    # as FAILED used to emit nothing at all -- the module has had no logger
    # since it was written -- so a backlog of stranded jobs looked identical to
    # a quiet, healthy system.
    if swept or timed_out:
        logger.warning(
            "agent-kv sweep terminalized %s never-dispatched and %s stuck job(s); "
            "a non-zero count here means jobs were stranded and their "
            "concurrency slots held",
            swept,
            timed_out,
        )
    else:
        logger.info("agent-kv sweep: nothing to terminalize")
    return {"swept": swept, "timed_out": timed_out}


def run_ttl_cleanup() -> dict:
    """Delete staged files for expired jobs and blank their refs (spec §5.4).

    The job row itself is retained (audit trail) -- only the object-store
    paths are dropped, once nothing can read them any more (the status/
    result endpoints already 404 past ``expires_at`` -- Task 9). Blanking a ref
    after its file is deleted is what makes a repeat call a no-op: the filters
    below only match rows still carrying a non-blank ref, so a job already
    cleaned (or one that never staged an input/produced a result) drops out of
    the candidate set on the next pass.

    Platform-wide by design, same as :func:`run_sweep`.

    **Two queries, not one ordering.** Retaining a ref whose delete failed is
    what makes a retry possible at all, but it also means failed rows compete
    with new expirations for a capped batch, and either side can starve the
    other. Both directions were observed in review:

    - Oldest-expiry-first alone: 500 permanently-failing rows refill every
      batch and nothing newer is ever reached.
    - ``cleanup_failed_at NULLS FIRST`` (the first attempt at a fix): the
      mirror image -- 500 fresh expirations per tick fill every batch and the
      failures are never retried, so their files sit in storage indefinitely.

    One ordering cannot express "neither side starves the other", so the batch
    is split instead: retries get up to ``_TTL_RETRY_RESERVE`` slots, fresh
    rows get whatever is left. Each side is capped, so each side is guaranteed
    capacity whenever it has work.

    The split also buys a cheaper plan. Each query now sorts by ONE column
    ascending with a plain equality/IS NULL predicate on the index's leading
    column, so the ``(cleanup_failed_at, expires_at)`` index serves both
    directly. ``NULLS FIRST`` could not use it at all -- a btree index is
    ``NULLS LAST`` by default -- so Postgres had to sort every matching expired
    row before applying the limit, which grows with the backlog.
    """
    now = timezone.now()
    # TERMINAL only. Without this, a job still RUNNING past `expires_at` had
    # its staged input deleted out from under the executor -- the TTL is a
    # retention policy for finished work, not a kill switch for running work.
    # Reachable whenever a job is stuck non-terminal for longer than
    # AGENT_KV_RESULT_TTL_DAYS, which is precisely what the sweep's phase 2
    # exists to catch; the sweep terminalizes those first, and then this
    # cleans them.
    expired = (
        AgentKVJob.objects.filter(expires_at__lt=now)
        .filter(status__in=list(AgentKVJob.TERMINAL))
        .filter(Q(input_ref__gt="") | Q(result_ref__gt=""))
    )

    # Retries first, capped at the reserve so they cannot crowd out fresh work.
    # Oldest failure first, so failures rotate rather than one row absorbing
    # every retry.
    retries = list(
        expired.filter(cleanup_failed_at__isnull=False).order_by("cleanup_failed_at")[
            :_TTL_RETRY_RESERVE
        ]
    )
    # Fresh rows take the remaining capacity -- the full batch when there is
    # nothing to retry, which is the normal case.
    fresh = list(
        expired.filter(cleanup_failed_at__isnull=True).order_by("expires_at")[
            : _MAINTENANCE_BATCH_LIMIT - len(retries)
        ]
    )

    cleaned = 0
    retained = 0
    for job in retries + fresh:
        # Blank only the refs whose files are CONFIRMED gone. Targeted
        # single-row update (not a queryset-wide `.update()`) for the same
        # reason it always was: one job's refs must never be blanked off the
        # back of another job's delete.
        #
        # A ref left set is the retry handle -- this loop used to blank both
        # unconditionally, so a transient object-store failure orphaned the file
        # permanently (the candidate filters above only match rows that still
        # carry a non-blank ref, so a blanked row can never be reconsidered).
        cleared = delete_job_files(job)
        fields: dict = dict.fromkeys(cleared, "")
        if len(cleared) == 2:
            cleaned += 1
            # Fully cleaned rows drop out of the candidate filter anyway (both
            # refs blank), so this only matters for a row that failed before and
            # succeeded now -- it must not keep a stale failure marker, or it
            # would consume a reserve slot it no longer needs.
            fields["cleanup_failed_at"] = None
        else:
            retained += 1
            # Stamped on every failed attempt, not just the first: this is what
            # moves the row into the retry lane, and refreshing it rotates the
            # retry order among failures instead of letting the earliest-stamped
            # row be retried forever.
            fields["cleanup_failed_at"] = timezone.now()
        AgentKVJob.objects.filter(id=job.id).update(**fields)
    # `retained` is reported, not just logged: these rows keep their refs and
    # are retried from the reserve lane on a later tick. A `retained` that
    # stays high across ticks is the signal that something is wrong with the
    # object store rather than with one job -- the split stops either side
    # blocking the other, it does not make a persistent fault harmless.
    # `retained` is the count this pass could NOT clean -- a file delete that
    # failed keeps its ref so the next pass retries it. A `retained` that never
    # falls is a stuck object, and stays invisible without this.
    if retained:
        logger.warning(
            "agent-kv TTL cleanup removed %s job(s) and RETAINED %s whose files "
            "could not be deleted; those refs are kept for the next pass",
            cleaned,
            retained,
        )
    elif cleaned:
        logger.info("agent-kv TTL cleanup removed %s expired job(s)", cleaned)
    return {"cleaned": cleaned, "retained": retained}
