"""Schedule-ownership ramp control (Phase 9, ②c) — hands a pipeline's schedule
from Celery Beat to the Postgres scheduler, per-schedule and reversibly.

A schedule is owned by exactly one firer. ``reconcile_schedule_ownership``
applies that decision atomically:

    pg_periodic_schedule.pg_owned  = resolve_schedule_owner(...)   # PG fires it
    PeriodicTask.enabled           = active AND NOT pg_owned       # Beat fires it

Doing both in one transaction is what makes "never double-fires" real (it was
*conditional* on this slice): a ``pg_owned`` row always has its Beat
``PeriodicTask`` disabled, so the two can't both fire.

Inert by default: ``resolve_schedule_owner`` fails closed to Beat
(``pg_owned=False``) until ops turns the master gate on AND ramps the
``pg_scheduler_enabled`` Flipt flag — so reconciling on every schedule edit is a
no-op (everything stays Beat-owned) until the rollout starts.
"""

from __future__ import annotations

import logging
import os

from django.conf import settings
from django.db import transaction
from django_celery_beat.models import PeriodicTask
from pg_queue.models import PgPeriodicSchedule

from unstract.flags.feature_flag import check_feature_flag_status

logger = logging.getLogger(__name__)

# Independent of the execution-transport flag (pg_queue_execution_enabled) so
# scheduling and execution ramp separately. %-rollout keyed on pipeline_id.
SCHEDULER_FLAG_KEY = "pg_scheduler_enabled"


def resolve_schedule_owner(pipeline_id: str, organization_id: str | None) -> bool:
    """True → the PG scheduler owns this schedule; False → Celery Beat does.

    Mirrors ``resolve_transport``: master-gated by ``PG_QUEUE_TRANSPORT_ENABLED``
    (shared PG kill-switch), then the ``pg_scheduler_enabled`` Flipt flag, keyed
    on ``pipeline_id`` for a stable percentage bucket. **Fails closed to Beat**
    on a closed gate, a blind Flipt, or any error — so a schedule never silently
    loses its firer.
    """
    # Master gate off → never consult Flipt; every schedule stays on Beat.
    if not settings.PG_QUEUE_TRANSPORT_ENABLED:
        return False

    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        logger.warning(
            "resolve_schedule_owner: gate ON but FLIPT_SERVICE_AVAILABLE != true "
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
            SCHEDULER_FLAG_KEY, entity_id=str(pipeline_id), context=context
        )
    except Exception:
        logger.exception(
            "resolve_schedule_owner: Flipt check failed for pipeline %s; "
            "leaving on Beat",
            pipeline_id,
        )
        return False
    return bool(owned)


def reconcile_ownership_for(
    pipeline_id: str, organization_id: str | None, active: bool
) -> bool:
    """Align one schedule's firer (Beat vs PG) with the current rollout decision.

    In one transaction: set ``pg_owned`` from :func:`resolve_schedule_owner` and
    set the Beat ``PeriodicTask.enabled = active AND NOT pg_owned`` — so a
    schedule handed to PG has Beat disabled (and vice-versa on rollback), with no
    window where both fire. ``organization_id`` is the org *identifier* string
    (what the mirror stores), used for Flipt per-org segmenting. Best-effort: a
    failure is logged and swallowed so it can never break the caller; the
    schedule stays on its current firer until the next reconcile. Returns the
    resolved ``pg_owned``.
    """
    pg_owned = resolve_schedule_owner(pipeline_id, organization_id)
    try:
        with transaction.atomic():
            # The mirror row exists from the dual-write (②a) / backfill; guard
            # anyway — a missing row means nothing to own yet.
            updated = PgPeriodicSchedule.objects.filter(pipeline_id=pipeline_id).update(
                pg_owned=pg_owned
            )
            if updated == 0:
                logger.info(
                    "reconcile_ownership_for: no mirror row for pipeline %s "
                    "(not yet mirrored); skipping",
                    pipeline_id,
                )
                return pg_owned
            # Beat owns it only when active AND not handed to PG.
            PeriodicTask.objects.filter(name=pipeline_id).update(
                enabled=active and not pg_owned
            )
        logger.info(
            "reconcile_ownership_for: pipeline %s pg_owned=%s (beat_enabled=%s)",
            pipeline_id,
            pg_owned,
            active and not pg_owned,
        )
    except Exception:
        logger.exception(
            "reconcile_ownership_for failed for pipeline %s — schedule stays on "
            "its current firer until the next reconcile",
            pipeline_id,
        )
    return pg_owned
