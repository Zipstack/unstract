"""Fairness key — multi-tenant routing metadata attached to every dispatch.

The key is **emitted** by every producer today; **read** by no one yet.
A later phase (PG Queue Gate) introduces the consumer: the PG Queue
fairness scheduler will route by ``org_id`` (per-tenant partition),
``pipeline_priority`` (within-tenant ordering), and ``tier`` (cross-tier
preemption / capacity allocation).

Until then the field sits inertly inside the task's ``kwargs`` under the
``_fairness_key`` slot — underscored to mark it as routing metadata,
not business payload.

This module is additive-only:

* No worker code reads ``_fairness_key`` today (verified by
  ``test_fairness_key.py``).
* A producer that omits the field is still accepted by ``dispatch()`` —
  the inventory canary in the characterisation suite is the place that
  forbids omission in production code paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Default values used when the caller has no better signal — e.g. system
# tasks (log persistence) that aren't tied to a specific org or pipeline.
DEFAULT_PRIORITY: Final[int] = 50
DEFAULT_TIER: Final[str] = "standard"

# Underscore-prefixed key so it's visually distinct from business kwargs
# in Celery introspection (Flower, ``inspect.active()``) and so a
# downstream task body doing ``**kwargs`` reflection has a clean
# convention for skipping routing metadata.
FAIRNESS_KWARG_NAME: Final[str] = "_fairness_key"


@dataclass(frozen=True)
class FairnessKey:
    """Routing metadata attached to every ``dispatch(...)``.

    ``org_id=None`` is a valid value — it denotes a system / cross-org
    task that doesn't belong to a tenant partition (e.g. periodic log
    flushing, healthchecks). PG Queue's scheduler treats those as a
    distinct "system" partition rather than as belonging to any tenant.
    """

    org_id: str | None
    pipeline_priority: int = DEFAULT_PRIORITY
    tier: str = DEFAULT_TIER

    def to_dict(self) -> dict[str, str | int | None]:
        """JSON-safe representation suitable for ``kwargs["_fairness_key"]``."""
        return {
            "org_id": self.org_id,
            "pipeline_priority": self.pipeline_priority,
            "tier": self.tier,
        }

    @classmethod
    def system(cls) -> FairnessKey:
        """Fairness key for a task with no tenant context."""
        return cls(org_id=None)

    @classmethod
    def for_org(cls, org_id: str | None, **overrides: object) -> FairnessKey:
        """Convenience constructor for the common case: a known org_id
        and defaults for the rest.
        """
        return cls(
            org_id=org_id,
            pipeline_priority=int(overrides.get("pipeline_priority", DEFAULT_PRIORITY)),
            tier=str(overrides.get("tier", DEFAULT_TIER)),
        )
