"""Fairness key — multi-tenant routing metadata attached to every dispatch.

The key is **emitted** by every producer today; **read** by no one yet.
A later phase (PG Queue Gate) introduces the consumer: the PG Queue
fairness scheduler will route by ``org_id`` (per-tenant partition),
``pipeline_priority`` (within-tenant ordering), and ``tier`` (cross-tier
preemption / capacity allocation).

Until then the field travels in the Celery message header
``x-fairness-key`` — out-of-band of the task body's kwargs, so a task
whose signature does not accept ``**kwargs`` doesn't blow up on the
extra field. On the consumer side it's reachable via
``self.request.headers["x-fairness-key"]`` when needed.

This module is additive-only:

* No worker code reads ``x-fairness-key`` today (verified by
  ``test_fairness_key.py::TestNoConsumerYet``).
* A producer that omits the field is still accepted by ``dispatch()`` —
  the inventory canary in the characterisation suite is the place that
  forbids omission in production code paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

# Closed vocabulary for ``tier``. Phase 8's scheduler matches on this
# set; widening the set is an explicit decision (e.g. add a new tenant
# class), not a typo. ``"system"`` is the special partition for tasks
# without tenant context (periodic log flush, healthchecks, etc.).
Tier = Literal["standard", "enterprise", "system"]

# Bounds for ``pipeline_priority``. The scheduler interprets 0..100 with
# higher = sooner; anything outside this range is rejected at
# construction so producers can't accidentally invent edge values that
# Phase 8 then has to special-case.
MIN_PRIORITY: Final[int] = 0
MAX_PRIORITY: Final[int] = 100

# Default values used when the caller has no better signal — e.g. a
# request with no per-pipeline priority configured.
DEFAULT_PRIORITY: Final[int] = 50
DEFAULT_TIER: Final[Tier] = "standard"
SYSTEM_TIER: Final[Tier] = "system"

# Celery message-header slot that carries the fairness key. Headers
# travel with the AMQP message but are NOT passed to the task body's
# function signature — exactly what we want for routing metadata.
# (Earlier iteration of this module put the key in ``kwargs``; that
# blew up tasks whose signature didn't accept ``**kwargs``.)
FAIRNESS_HEADER_NAME: Final[str] = "x-fairness-key"


@dataclass(frozen=True)
class FairnessKey:
    """Routing metadata attached to every ``dispatch(...)``.

    ``org_id=None`` is a valid value — it denotes a system / cross-org
    task that doesn't belong to a tenant partition (e.g. periodic log
    flushing, healthchecks). Producers building those keys should also
    set ``tier="system"`` (see :meth:`FairnessKey.system`) so the Phase 8
    scheduler can match on the tier alone, without special-casing
    ``org_id is None``.

    ``pipeline_priority`` is bounded to ``MIN_PRIORITY..MAX_PRIORITY``
    (0..100). Higher = sooner.
    """

    org_id: str | None
    pipeline_priority: int = DEFAULT_PRIORITY
    tier: Tier = DEFAULT_TIER

    def __post_init__(self) -> None:
        if not MIN_PRIORITY <= self.pipeline_priority <= MAX_PRIORITY:
            raise ValueError(
                "pipeline_priority out of range "
                f"[{MIN_PRIORITY}, {MAX_PRIORITY}]: {self.pipeline_priority}"
            )

    def to_dict(self) -> dict[str, str | int | None]:
        """JSON-safe representation carried in the Celery message header
        ``x-fairness-key``.
        """
        return {
            "org_id": self.org_id,
            "pipeline_priority": self.pipeline_priority,
            "tier": self.tier,
        }

    @classmethod
    def system(cls) -> FairnessKey:
        """Fairness key for a task with no tenant context.

        ``tier="system"`` encodes the partition in the message itself
        (rather than leaving it implicit via ``org_id is None``), so the
        future PG Queue scheduler matches on a single closed-set field.
        """
        return cls(org_id=None, tier=SYSTEM_TIER)

    @classmethod
    def for_org(
        cls,
        org_id: str,
        *,
        pipeline_priority: int = DEFAULT_PRIORITY,
        tier: Tier = DEFAULT_TIER,
    ) -> FairnessKey:
        """Convenience constructor for the common case: a known org_id
        and defaults for the rest.

        Keyword-only overrides (no ``**kwargs``) so a typo like
        ``priority=80`` or ``tiers="enterprise"`` raises ``TypeError``
        at the call site instead of silently dropping the override.

        ``org_id`` is required and non-None. For tasks without tenant
        context use :meth:`FairnessKey.system` — passing a missing org
        through here would produce an inconsistent key (``org_id=None``
        with ``tier="standard"``) that Phase 8 would have to
        special-case.
        """
        if org_id is None:
            raise ValueError(
                "org_id must not be None for org-bound tasks; "
                "use FairnessKey.system() for tasks without tenant context."
            )
        return cls(
            org_id=org_id,
            pipeline_priority=pipeline_priority,
            tier=tier,
        )
