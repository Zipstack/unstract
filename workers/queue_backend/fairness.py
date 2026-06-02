"""Fairness key — multi-tenant routing metadata attached to every dispatch.

The key is emitted by every producer today; no consumer reads it yet.
When a future dispatch scheduler comes online, it will route by
``org_id`` (per-tenant partition), ``pipeline_priority`` (within-tenant
ordering), and ``tier`` (cross-tier preemption / capacity allocation).

The field travels in the Celery message header ``x-fairness-key`` —
out-of-band of the task body's kwargs, so a task whose signature does
not accept ``**kwargs`` isn't broken by the extra field. Consumers
reach it via ``self.request.headers["x-fairness-key"]`` on bound tasks.

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

# Tier is a cross-tenant resource-allocation tag. The future dispatch
# scheduler uses it for preemption and capacity allocation across orgs
# (e.g. enterprise traffic shouldn't be blocked by standard traffic
# during contention). Closed vocabulary so typos become type errors
# rather than silent new partitions. ``"system"`` is the partition for
# tasks with no tenant context (periodic log flush, healthchecks).
Tier = Literal["standard", "enterprise", "system"]

# Bounds for ``pipeline_priority`` (0..100, higher = sooner). Enforced
# at construction so the wire contract stays closed.
MIN_PRIORITY: Final[int] = 0
MAX_PRIORITY: Final[int] = 100

# Defaults when the caller has no better signal.
DEFAULT_PRIORITY: Final[int] = 50
DEFAULT_TIER: Final[Tier] = "standard"
SYSTEM_TIER: Final[Tier] = "system"

# Celery message-header slot that carries the fairness key. Headers
# travel with the AMQP message but are not passed to the task body's
# function signature — exactly what we want for routing metadata.
FAIRNESS_HEADER_NAME: Final[str] = "x-fairness-key"


@dataclass(frozen=True)
class FairnessKey:
    """Routing metadata attached to every ``dispatch(...)``.

    ``org_id=None`` is valid for system / cross-org tasks (periodic log
    flushing, healthchecks). Producers building those keys should use
    :meth:`FairnessKey.system` so ``tier="system"`` rides along — the
    scheduler then matches on a single closed-set field instead of
    special-casing ``org_id is None``.

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
        rather than leaving it implicit via ``org_id is None``, so the
        scheduler matches on a single closed-set field.
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
