"""Terminalise executions that were created but never dispatched to a queue.

``PENDING`` is not a terminal state, so every execution must eventually reach
``COMPLETED`` or ``ERROR``. One case had no owner:

    deployment_helper.py:236   create_workflow_execution(...)   -> commits a PENDING row
       ... file handling, validation ...
    deployment_helper.py:310   execute_workflow_async(...)      -> dispatches

An abort between those two — client disconnect, gateway timeout, pod eviction, OOM —
leaves a committed ``PENDING`` row that was never queued. Nothing recovers it:

* the **reaper** recovers stranded work by scanning ``pg_barrier_state``, and a barrier
  only exists once a batch has been dispatched. No dispatch, no barrier, invisible.
* ``execute_workflow_async`` marks *dispatch failures* ERROR, but never runs at all if
  the request dies before reaching it.

Observed on integration 2026-08-17: an 800-user load test saturated the API tier
(2 backend pods), 71% of requests got a 502 from the load balancer, and **967
executions were left PENDING** — 2914 execution rows from 2444 requests, because the
row outlived the request. ``pg_queue_message`` was completely empty, confirming the
work was never enqueued rather than enqueued-and-lost.

**Not PG-specific.** The create-then-dispatch ordering sits *upstream* of transport
selection, so the Celery path had the identical window (UN-4046 removed that path;
the predicate stays transport-aware because rows dispatched before the upgrade carry
``task_id`` rather than ``queue_message_id``).

**The predicate.** ``workflow_helper.py:566/570`` stamps ``queue_message_id`` (PG) or
``task_id`` (Celery) immediately after a successful dispatch, and the model documents
that the other stays NULL. So ``PENDING`` + both handles NULL + older than the grace
period means the dispatch USUALLY never happened — but see the note in
_release_abandoned_resources: three paths in workflow_helper reach that exact
state AFTER dispatch, which is why this sweep does no irreversible cleanup and
why the real fix is a positive dispatched_at rather than an inferred absence.
Do not shorten the grace period or reinstate cleanup on the strength of this
paragraph alone. Nominally it means the dispatch never happened — no JSONB probing, no cross-table joins, and
correct under either transport.
"""

from __future__ import annotations

import logging
import os

from django.utils import timezone

from unstract.core.data_models import ExecutionStatus

logger = logging.getLogger(__name__)

# Grace period before an undispatched execution is considered abandoned.
#
# Dispatch normally follows row creation within seconds, so this is generous by two
# orders of magnitude. It has to be: the ONLY thing separating "abandoned" from "about
# to be dispatched" is elapsed time, and terminalising a live execution is far worse
# than leaving a dead one a while longer. Well under the barrier stuck-timeout (~2.5h)
# so the two sweeps never contend for the same row.
# RAISED 900 -> 3600 deliberately, and the reason is PG-specific.
#
# The predicate cannot distinguish "never dispatched" from "dispatched, handle not
# recorded, message still sitting in the queue" — see the note in
# _release_abandoned_resources for the three paths that produce the second state. On
# CELERY that mismatch was survivable: the orchestrator runs on the row regardless and
# its terminal write supersedes the sweep's ERROR. On PG it is not. Both worker entry
# points STOP on a terminal execution (general/tasks.py returns
# skipped_terminal_execution; file_processing/tasks.py raises _TerminalExecutionSkip),
# so a row this sweep terminalises while its message is still queued gets acked and
# dropped rather than run.
#
# That failure needs a slow queue AND an unrecorded handle at once. An hour is chosen to
# sit well clear of any realistic dequeue latency, which is what shrinks the overlap to
# near-nothing without new machinery. It is a mitigation, not the fix: the fix is to make
# dispatch a POSITIVE fact (a stamped dispatched_at) so the predicate stops guessing.
#
# Still well under the barrier stuck-timeout (~2.5h), so the two sweeps never contend for
# the same row. Cost of the raise: a genuinely undispatched execution shows PENDING for
# up to an hour before it errors. Override per-environment with the env var if a
# deployment's queue latency justifies something tighter.
_MIN_AGE_ENV = "UNDISPATCHED_EXECUTION_GRACE_SECONDS"
DEFAULT_MIN_AGE_SECONDS = 3600  # 1 hour

# Bounds one sweep so a large backlog (a 502 storm leaves hundreds) can't hold a long
# transaction open. Whatever is left is picked up by the next tick.
_BATCH_LIMIT_ENV = "UNDISPATCHED_EXECUTION_SWEEP_LIMIT"
DEFAULT_BATCH_LIMIT = 500

# USER-FACING. `error_message` is rendered in the UI: ExecutionSerializer uses
# `exclude`, not `fields`, so every unlisted model field is serialized — this string
# reaches customers. It answers their three questions (did anything run? is my data
# affected? what do I do?) and deliberately names no internals: no queues, barriers,
# dispatch or gateways. The machine-readable ref is for support/greppability, and the
# precise technical cause stays in the log line below.
#
# Must fit EXECUTION_ERROR_LENGTH (256); the model truncates silently, which would
# otherwise eat the ref code at the end.
UNDISPATCHED_ERROR_MESSAGE = (
    "This execution did not start. The request was interrupted before any processing "
    "began, so no files were processed. You can safely run it again. "
    "(ref: EXEC_NOT_STARTED)"
)


def _positive_int_from_env(name: str, default: int) -> int:
    """Env override, falling back loudly rather than silently on a bad value.

    A shortened grace period is the dangerous direction (it terminalises live
    executions), so a typo must not quietly take effect.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r is not an integer; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%r must be > 0; using default %s", name, raw, default)
        return default
    return value


# Claim the batch in ONE statement that also reports exactly which rows it won.
#
# `UPDATE ... RETURNING` is the whole design in a single round trip:
#   * the inner SELECT bounds the batch and takes row locks (SKIP LOCKED, so an
#     overlapping sweeper can never block or double-claim);
#   * the OUTER WHERE re-carries the full predicate, so Postgres re-evaluates it at
#     write time under those locks — a row dispatched between selection and write is
#     silently skipped rather than marked ERROR *while it runs*, which is the one
#     failure this sweep must never cause;
#   * RETURNING yields precisely the claimed rows, which is what lets the irreversible
#     cleanup run for those and only those. (An earlier draft looped one UPDATE per
#     row to get that guarantee; this keeps it and drops 500 round trips.)
#
# Django's .update() cannot RETURN rows, hence raw SQL — the same approach the PG-queue
# reaper's own sweeps use. The table name is interpolated from _meta (never user input).
_CLAIM_SQL = """
UPDATE {table}
   SET status = %s, error_message = %s, modified_at = %s
 WHERE id IN (
         SELECT id
           FROM {table}
          WHERE status = %s
            AND created_at < %s
            AND dispatched_at IS NULL
            AND task_id IS NULL
            AND queue_message_id IS NULL
          ORDER BY created_at
          LIMIT %s
          FOR UPDATE SKIP LOCKED
       )
   AND status = %s
   AND dispatched_at IS NULL
   AND task_id IS NULL
   AND queue_message_id IS NULL
RETURNING id, workflow_id
"""


def sweep_undispatched_executions(
    min_age_seconds: int | None = None, limit: int | None = None
) -> int:
    """Mark aged, never-dispatched PENDING executions ERROR. Returns the count.

    Idempotent and safe to run on every sweep: a row that has since been dispatched or
    terminalised no longer matches the predicate, so a second pass finds nothing.

    Race-free by construction — see :data:`_CLAIM_SQL`.
    """
    from django.db import connection

    from workflow_manager.workflow_v2.models import WorkflowExecution

    min_age = min_age_seconds or _positive_int_from_env(
        _MIN_AGE_ENV, DEFAULT_MIN_AGE_SECONDS
    )
    batch_limit = limit or _positive_int_from_env(_BATCH_LIMIT_ENV, DEFAULT_BATCH_LIMIT)
    now = timezone.now()
    cutoff = now - timezone.timedelta(seconds=min_age)

    sql = _CLAIM_SQL.format(table=WorkflowExecution._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            [
                ExecutionStatus.ERROR.value,
                UNDISPATCHED_ERROR_MESSAGE,
                now,
                ExecutionStatus.PENDING.value,
                cutoff,
                batch_limit,
                ExecutionStatus.PENDING.value,
            ],
        )
        claimed = cursor.fetchall()

    if not claimed:
        return 0

    for execution_id, workflow_id in claimed:
        _release_abandoned_resources(str(execution_id), str(workflow_id))

    # The operator-facing half of the story. The user-facing column says only what a
    # customer needs; the cause belongs here, where it can name internals freely.
    logger.error(
        "Undispatched-execution sweep: marked %s execution(s) ERROR. They were created "
        "but never queued (task_id and queue_message_id both NULL) and exceeded the %ss "
        "grace period — the request died between create_workflow_execution and "
        "execute_workflow_async. Ids: %s",
        len(claimed),
        min_age,
        ", ".join(str(row[0]) for row in claimed[:20]),
    )
    return len(claimed)


def _release_abandoned_resources(execution_id: str, workflow_id: str) -> None:
    """Do what the abort prevented the request's own error path from doing.

    ``deployment_helper`` releases the rate-limit slot and deletes the API storage dir
    when staging *raises*. An abort raises nothing — the thread is simply gone — so
    neither runs and the execution leaks both.

    **Best-effort, and deliberately so.** The status write already succeeded and is the
    part that matters; a failure to tidy up must never propagate and stall the rest of
    the batch.

    Only the slot is released here. The staged input is deliberately retained — see the
    note in the body for why, and why re-adding that delete needs the predicate fixed
    first.
    """
    # Slot first: it is the one with a live cost. Held slots consume the org's API
    # deployment concurrency budget until the Redis ZSET TTL (6h) expires them, so a
    # 502 storm can throttle a tenant for hours. Self-healing, but slowly.
    try:
        from api_v2.rate_limiter import APIDeploymentRateLimiter

        from workflow_manager.workflow_v2.models import WorkflowExecution

        organization = (
            WorkflowExecution.objects.select_related("workflow__organization")
            .get(id=execution_id)
            .workflow.organization
        )
        # str(...organization_id), NOT the model instance. release_slot builds its Redis
        # key by formatting the argument into "api_deployment:rate_limit:org:{org_id}",
        # and acquire_slot built it from str(organization.organization_id). Passing the
        # instance yields "...:org:Organization object (12)", which matches nothing — the
        # ZREM removes a non-member, returns 0, raises nothing, and the slot stays held
        # for the full 6h TTL. Silent, and the exact harm this call exists to prevent.
        APIDeploymentRateLimiter.release_slot(
            str(organization.organization_id), execution_id
        )
    except Exception:
        logger.warning(
            "Undispatched sweep: could not release the rate-limit slot for %s "
            "(it expires with the limiter TTL regardless)",
            execution_id,
            exc_info=True,
        )

    # The staged input is deliberately NOT deleted here.
    #
    # This sweep infers "never dispatched" from the ABSENCE of both handles
    # (task_id IS NULL AND queue_message_id IS NULL). That inference is not sound:
    # three paths in workflow_helper leave a RUNNING execution in exactly that state,
    # all of them after the message is already on its transport —
    #
    #   * _record_dispatch_handle raises and the caller swallows it, explicitly
    #     "continuing — the orchestrator is already running" (workflow_helper.py:686)
    #   * the handle comes back empty and it returns without writing (:544)
    #   * a PG handle will not parse as a bigint and it returns without writing (:562)
    #
    # so after the 15-minute grace this sweep can claim a live execution.
    #
    # Do NOT read the surviving ERROR write as harmless. An earlier version of this note
    # claimed it "self-corrects — the running worker's own terminal write supersedes it".
    # That is false on the PG transport: both worker entry points treat a terminal
    # execution as a reason to STOP, not to overwrite. general/tasks.py returns
    # skipped_terminal_execution before it would write EXECUTING, and
    # file_processing/tasks.py raises _TerminalExecutionSkip. So a wrongly-claimed row is
    # silently DROPPED — the message is acked, no retry is scheduled, and the only trace
    # is a worker WARNING. The realistic trigger is not the three no-handle paths above
    # but a saturated queue: a message enqueued successfully and still unconsumed at 15
    # minutes gets marked ERROR and then discarded, under exactly the backlog conditions
    # that produced the orphans this sweep was built for.
    #
    # Even where a terminal write does land, error_message is not cleared by it, so a
    # wrongly-claimed run can complete while still showing the customer "This execution
    # did not start... You can safely run it again."
    #
    # Deleting the input is worse again and is what this removal addresses: the worker is
    # still going to read it, and the message invites a re-run against data that is gone.
    #
    # Dropping the delete keeps the reversible half of the sweep and removes the
    # irreversible one, at the cost of leaking an input directory for executions that
    # genuinely never started. That is the right trade while the predicate is unsound;
    # the real fix is to make dispatch a POSITIVE fact (stamp dispatched_at in the same
    # call that records the handle, including on the three branches above, and key both
    # this predicate and the 0026 partial index on it) — tracked separately, since it
    # needs a migration and an index rebuild.
    _ = workflow_id  # retained: the signature is restored with the positive-fact fix
