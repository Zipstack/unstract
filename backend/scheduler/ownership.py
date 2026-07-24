"""Schedule-ownership ramp control — hands a pipeline's schedule
from Celery Beat to the Postgres scheduler, per-schedule and reversibly.

A schedule is owned by exactly one firer. ``reconcile_ownership_for``
applies that decision atomically:

    pg_periodic_schedule.pg_owned  = resolve_schedule_owner(...)   # PG fires it
    PeriodicTask.enabled           = active AND NOT pg_owned       # Beat fires it

Doing both in one transaction is what makes "never double-fires" real (it was
*conditional* on this slice): a ``pg_owned`` row always has its Beat
``PeriodicTask`` disabled, so the two can't both fire.

Inert by default: ``resolve_schedule_owner`` fails closed to Beat
(``pg_owned=False``) until ops ramps the single ``pg_queue_enabled`` Flipt flag — so
reconciling on every schedule edit is a no-op (everything stays Beat-owned) until the
rollout starts.
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


def resolve_schedule_owner(pipeline_id: str, organization_id: str | None) -> bool:
    """True → the PG scheduler owns this schedule; False → Celery Beat does.

    Mirrors ``resolve_transport``: gated by the single ``pg_queue_enabled`` Flipt
    flag, keyed on ``pipeline_id`` for a stable percentage bucket. **Fails closed to
    Beat** on a blind Flipt or any error — so a schedule never silently loses its
    firer.
    """
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
            "resolve_schedule_owner: Flipt check failed for pipeline %s; "
            "leaving on Beat",
            pipeline_id,
            exc_info=True,
        )
        return False
    return bool(owned)


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
    """
    pg_owned = resolve_schedule_owner(pipeline_id, organization_id)
    try:
        with transaction.atomic():
            # queryset .update() doesn't fire auto_now, so bump updated_at
            # explicitly (mirrors _mirror_periodic_schedule_set_enabled).
            updates: dict = {"pg_owned": pg_owned, "updated_at": timezone.now()}
            if not pg_owned:
                # Back on Beat → clear the PG next-run so a future re-hand-over
                # baselines instead of firing immediately on a stale timestamp.
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
            PeriodicTask.objects.filter(name=pipeline_id).update(
                enabled=active and not pg_owned
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
