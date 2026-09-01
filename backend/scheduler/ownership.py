"""Schedule-ownership ramp control — hands a pipeline's schedule
from Celery Beat to the Postgres scheduler, per-schedule and reversibly.

A schedule is owned by exactly one firer. ``reconcile_ownership_for``
applies that decision atomically:

    pg_periodic_schedule.pg_owned  = resolve_schedule_owner(...)   # PG fires it
    PeriodicTask.enabled           = active AND NOT pg_owned       # Beat fires it

Doing both in one transaction is what makes "never double-fires" real (it was
*conditional* on this slice): a ``pg_owned`` row always has its Beat
``PeriodicTask`` disabled, so the two can't both fire.

**Two gates, and both must be on.** ``PG_SCHEDULER_ENABLED`` (env, default off) comes
first; the ``pg_queue_enabled`` Flipt flag then decides per schedule, failing closed to
Beat on a blind Flipt or any error.

They are separate because Beat stays the **sole scheduler for the whole PG rollout**:
pipelines already reach PG without this module (``execute_pipeline_task_v2`` →
``complete_execution`` → ``execute_workflow_async`` → ``resolve_transport``), so the PG
scheduler exists only to retire the Beat *deployment* — a later, deliberate step. While
the env gate is off this module writes **nothing at all**, so Beat's tables are untouched
for the entire rollout and turning the flag off again is a pure Flipt flip with nothing
to restore.
"""

from __future__ import annotations

import logging
import os

from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import PeriodicTask, PeriodicTasks
from pg_queue.flags import PG_QUEUE_FLAG_KEY
from pg_queue.models import PgPeriodicSchedule
from unstract.flags.feature_flag import check_feature_flag_status

logger = logging.getLogger(__name__)

# Gating uses the single shared PG-queue flag (pg_queue.flags.PG_QUEUE_FLAG_KEY,
# imported above) — one flip gates execution + scheduler + executor. The scheduler
# buckets the %-rollout on pipeline_id (each subsystem keys on its own entity).


# Second gate, ahead of the Flipt flag: hand-over to the PG scheduler happens only
# when this is explicitly on. Referenced as "pg_scheduler_enabled" by this module's
# callers' comments (scheduler/helper.py, reconcile_pg_schedules) since the ramp was
# designed, but never actually implemented — resolve_schedule_owner gated on
# pg_queue_enabled alone, so the two flips were welded together.
#
# They must be separable, because Beat stays the SOLE scheduler for the whole PG
# rollout: pipelines already reach PG without it (execute_pipeline_task_v2 →
# complete_execution → execute_workflow_async → resolve_transport), so the PG
# scheduler exists only to retire the Beat *deployment* — a later, deliberate step.
#
# Without this gate, turning pg_queue_enabled on would hand schedules to a PG
# scheduler that is not running: reconcile_ownership_for disables the Beat
# PeriodicTask, nothing polls the PG side, and the pipeline has no firer at all. It
# runs in the backend on every schedule save, so scaling Beat to zero does not avoid
# it and no ramp command is needed to trigger it — a user saving a schedule suffices.
_PG_SCHEDULER_ENABLED_ENV = "PG_SCHEDULER_ENABLED"


def pg_scheduler_enabled() -> bool:
    """Whether schedule hand-over to the PG scheduler is switched on at all.

    Defaults **off**. Flip it only alongside deploying the PG scheduler worker, as
    part of retiring Celery Beat.
    """
    return os.environ.get(_PG_SCHEDULER_ENABLED_ENV, "false").strip().lower() == "true"


def resolve_schedule_owner(pipeline_id: str, organization_id: str | None) -> bool:
    """True → the PG scheduler owns this schedule; False → Celery Beat does.

    Mirrors ``resolve_transport``: gated by the single ``pg_queue_enabled`` Flipt
    flag, keyed on ``pipeline_id`` for a stable percentage bucket. **Fails closed to
    Beat** on a blind Flipt or any error — so a schedule never silently loses its
    firer.

    Requires ``PG_SCHEDULER_ENABLED`` **as well as** the flag: during the PG rollout
    the flag is on while the PG scheduler is still dark, and a schedule handed to a
    scheduler that is not running would simply stop firing.
    """
    if not pg_scheduler_enabled():
        return False
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        logger.warning(
            "resolve_schedule_owner: FLIPT_SERVICE_AVAILABLE != true "
            "(Flipt blind) for pipeline %s; leaving on Beat",
            pipeline_id,
        )
        return False

    # Flipt context is a gRPC map<string,string>; coerce values to str (a non-str
    # makes the client swallow it as False). entity_id str-coerced too so the
    # %-rollout bucket is stable across str/UUID call sites.
    context = {"pipeline_id": str(pipeline_id)}
    if organization_id:
        context["organization_id"] = str(organization_id)
    try:
        owned = check_feature_flag_status(
            flag_key=PG_QUEUE_FLAG_KEY, entity_id=str(pipeline_id), context=context
        )
    except Exception:
        # Expected, recoverable (fail-closed to Beat) and runs on every schedule
        # edit — warn with traceback rather than logger.exception so a persistently
        # down Flipt doesn't bury real errors as a per-edit Sentry exception.
        logger.warning(
            "resolve_schedule_owner: Flipt check failed for pipeline %s; leaving on Beat",
            pipeline_id,
            exc_info=True,
        )
        return False
    return bool(owned)


def _has_stale_pg_ownership(pipeline_id: str) -> bool:
    """True if this row claims PG ownership while the gate is off — i.e. it needs
    releasing back to Beat.

    **Fails closed to today's behaviour**: on any DB error this returns False, so the
    caller takes the historical `return False` path and writes nothing. A repair that
    cannot confirm it is needed must not run.
    """
    try:
        return PgPeriodicSchedule.objects.filter(
            pipeline_id=pipeline_id, pg_owned=True
        ).exists()
    except Exception:
        logger.exception(
            "reconcile_ownership_for: could not check stale PG ownership for "
            "pipeline %s; leaving the schedule on its current firer",
            pipeline_id,
        )
        return False


def reconcile_ownership_for(
    pipeline_id: str, organization_id: str | None, *, active: bool
) -> bool | None:
    """Align one schedule's firer (Beat vs PG) with the current rollout decision.

    In one transaction: set ``pg_owned`` from :func:`resolve_schedule_owner` and
    set the Beat ``PeriodicTask.enabled = active AND NOT pg_owned`` — so a
    schedule handed to PG has Beat disabled (and vice-versa on rollback), with no
    window where both fire. On rollback (``pg_owned`` → False) ``next_run_at`` is
    also cleared so a later re-hand-over re-enters the PG tick's NULL baseline
    (no burst). ``organization_id`` is the org *identifier* string (what the
    mirror stores), used for Flipt per-org segmenting. ``active`` is keyword-only
    (a fire/don't-fire boolean trap otherwise).

    Best-effort: a DB failure is logged and swallowed so it can never break the
    caller. Returns the resolved ``pg_owned`` on success, or **None** if the
    transaction failed (so the ramp command can tally + surface failures).

    **No-op while ``PG_SCHEDULER_ENABLED`` is off** — writing NEITHER table, *unless*
    the row contradicts the gate (see below). Returning early rather than relying on
    ``resolve_schedule_owner`` returning False matters: that path would still issue
    ``PeriodicTask.update(enabled=active)`` and bump ``PeriodicTasks.update_changed()``
    on every schedule save, forcing a Beat reload to write back a value Beat already
    had. Beat's tables stay untouched for the whole rollout, so flag-off is a pure
    Flipt flip with nothing to restore.
    """
    if not pg_scheduler_enabled():
        # Gate off ⇒ Beat owns everything. ASSERT that instead of assuming it.
        #
        # The original blanket `return False` assumed pg_owned could never be True
        # while the gate is off. An image predating this gate breaks that assumption:
        # there, resolve_schedule_owner keys on the Flipt flag ALONE, so flipping
        # pg_queue_enabled hands schedules to PG. Roll forward onto this gate and the
        # row is stranded — writing nothing can never correct it, and NO code path
        # (not even `reconcile_pg_schedules` without --mirror-only, which routes back
        # through here) can clear it. Only hand-written SQL could, which is not a
        # deploy procedure. Observed on integration 2026-08-12: Beat and the PG
        # scheduler both fired one pipeline 2.4s apart; a single execution resulted
        # only because the Celery consumers happened to be scaled to zero.
        #
        # This is reachable in production WITHOUT a mis-built image: deploy this
        # branch, roll back to a pre-gate build while the flag is on, roll forward.
        # Rollback is precisely when a stranded scheduler is least affordable.
        #
        # Cost in the normal case is one indexed existence check and still zero
        # writes, so the "Beat's tables stay untouched" guarantee holds for every
        # environment that never had a contradictory row.
        if not _has_stale_pg_ownership(pipeline_id):
            return False
        logger.warning(
            "reconcile_ownership_for: pipeline %s is pg_owned while "
            "PG_SCHEDULER_ENABLED is off (stale hand-over from a pre-gate build); "
            "releasing it back to Beat",
            pipeline_id,
        )
        pg_owned = False
    else:
        pg_owned = resolve_schedule_owner(pipeline_id, organization_id)
    try:
        with transaction.atomic():
            was_pg_owned = (
                PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id)
                .values_list("pg_owned", flat=True)
                .first()
            )
            # queryset .update() doesn't fire auto_now, so bump updated_at
            # explicitly (mirrors _mirror_periodic_schedule_set_enabled).
            updates: dict = {"pg_owned": pg_owned, "updated_at": timezone.now()}
            # Baseline on an ownership CHANGE, in either direction. NULL means
            # "record a baseline next tick, don't fire this cycle"
            # (pg_queue/models.py:366), and that is the only thing standing between a
            # hand-over and an immediate unscheduled run: the tick selects
            # `WHERE pg_owned AND enabled AND (next_run_at IS NULL OR <= now())`, so a
            # next_run_at left over from an earlier PG-ownership period is already in
            # the past and fires at once. Observed on integration 2026-08-14 —
            # gallh_load_test carried next_run_at=2026-08-12 06:08 from a stale row and
            # fired ~2s after being re-enabled, two days late, alongside the operator's
            # manual run.
            #
            # Scoped to the TRANSITION, not every call: this runs on every pipeline
            # save, and clearing unconditionally would re-baseline mid-cycle — a save at
            # 12:07:59 against a 12:08 next_run_at would skip that fire entirely.
            handing_over_to_pg = pg_owned and not was_pg_owned
            if not pg_owned or handing_over_to_pg:
                updates["next_run_at"] = None
            # The mirror row exists from the dual-write / backfill; guard
            # anyway — a missing row means nothing to own yet.
            updated = PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).update(
                **updates
            )
            if updated == 0:
                logger.info(
                    "reconcile_ownership_for: no mirror row for pipeline %s "
                    "(not yet mirrored); skipping",
                    pipeline_id,
                )
                # Without a mirror row PG can't fire (nothing to tick) and the Beat
                # PeriodicTask was never disabled → the effective owner is Beat.
                # Return False so the ramp count isn't inflated past what's live.
                return False
            # Beat owns it only when active AND not handed to PG.
            beat_updates: dict = {"enabled": active and not pg_owned}
            # Baseline Beat's clock on the way BACK, for the same reason next_run_at
            # is baselined on the way out — and this half was missing.
            #
            # DatabaseScheduler keeps no next_run_at; it derives due-ness from
            # PeriodicTask.last_run_at against the crontab. A schedule that spent days
            # PG-owned carries a last_run_at from before the hand-over, so the instant
            # `enabled` flips back every missed interval is overdue and Beat replays
            # them at once. Observed on integration 2026-08-24: releasing 23 schedules
            # fired 4 pipelines plus 3 periodics within 30 ms of "Released to Beat".
            #
            # An earlier comment here asserted the opposite — that DatabaseScheduler
            # "recomputes due-ness from the crontab each tick, so re-enabling never
            # produced a catch-up run". That was wrong: it recomputes from last_run_at,
            # which is exactly what makes it catch up.
            #
            # Scoped to the RELEASE transition, mirroring the next_run_at rule above:
            # stamping it on every call would push the clock forward on an ordinary
            # pipeline save and silently skip a due fire.
            if was_pg_owned and not pg_owned:
                beat_updates["last_run_at"] = timezone.now()
            matched = PeriodicTask.objects.filter(name=pipeline_id).update(**beat_updates)
            if not matched:
                # Branch the WHOLE message, not just the verb. The two directions mean
                # opposite things, and an earlier version applied the alarming tail to
                # both — which is how the direction that matters gets filtered out.
                if pg_owned:
                    # Adopt: nothing to switch off. The mirror row was just written
                    # pg_owned=True and the PG tick selects WHERE pg_owned AND enabled,
                    # so PG *is* the firer. Benign, and this path runs on every pipeline
                    # save, so a warning here would be noise.
                    logger.info(
                        "reconcile_ownership_for: no Beat PeriodicTask named %s to "
                        "disable — PG owns it now, nothing needed switching off",
                        pipeline_id,
                    )
                else:
                    # Release: PG has let go and Beat has no row to take over, so the
                    # schedule has no firer at all — on the rollback path. Silent before
                    # this: a bulk .update() reports success by returning 0.
                    logger.warning(
                        "reconcile_ownership_for: no Beat PeriodicTask named %s to "
                        "release to — the schedule may now have no firer",
                        pipeline_id,
                    )
            # Bulk .update() bypasses django-celery-beat's post_save signal, so
            # PeriodicTasks.last_update never bumps and DatabaseScheduler never
            # reloads — Beat would keep firing the schedule from its stale
            # in-memory copy on a PG hand-over (breaking the no-double-fire
            # invariant) or never re-enable it on a rollback. Bump explicitly.
            PeriodicTasks.update_changed()
        logger.info(
            "reconcile_ownership_for: pipeline %s pg_owned=%s (beat_enabled=%s)",
            pipeline_id,
            pg_owned,
            active and not pg_owned,
        )
        return pg_owned
    except Exception:
        logger.exception(
            "reconcile_ownership_for failed for pipeline %s — schedule stays on "
            "its current firer until the next reconcile",
            pipeline_id,
        )
        return None
