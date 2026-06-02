"""Fairness key — multi-tenant routing metadata attached to every dispatch.

Three fields, matching the staging-queue columns + ORDER BY in the labs
PG Queue implementation guide
(`Zipstack/labs:labs-ali/workflow-execution-architecture/docs/pg-queue-implementation-guide.md`):

* ``org_id`` — per-tenant partition. Used server-side by the scheduler
  to JOIN against ``org_config`` and look up the tenant's
  ``tier_priority`` and ``burst_max``. (Tier itself is *not* on the
  task payload; it's an org-level lookup.)
* ``workload_type`` — ``"api"`` vs ``"etl"``. The scheduler's L2
  fairness check prefers ``api`` so customer-facing requests aren't
  blocked by background ETL.
* ``pipeline_priority`` — 1..10, higher = sooner. The scheduler's L3
  fairness check; tiebreaker within (tier, workload_type).

The key is emitted by every producer today; no consumer reads it yet.
When a future dispatch scheduler comes online (PG Queue + ``SELECT FOR
UPDATE SKIP LOCKED``), the same three fields drive its ORDER BY.

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

# Closed vocabulary for ``workload_type``. Matches the labs design's
# L2 fairness check (``(workload_type = 'api')::int DESC``). Anything
# that isn't customer-facing API traffic is ``etl``.
WorkloadType = Literal["api", "etl"]

# Bounds for ``pipeline_priority`` (1..10, higher = sooner) per the
# labs schema. Enforced at construction so the wire contract stays
# closed.
MIN_PRIORITY: Final[int] = 1
MAX_PRIORITY: Final[int] = 10
DEFAULT_PRIORITY: Final[int] = 5

# Celery message-header slot that carries the fairness key. Headers
# travel with the AMQP message but are not passed to the task body's
# function signature — exactly what we want for routing metadata.
FAIRNESS_HEADER_NAME: Final[str] = "x-fairness-key"


@dataclass(frozen=True)
class FairnessKey:
    """Routing metadata attached to every ``dispatch(...)``.

    ``org_id=None`` is valid for system / cross-org tasks (periodic log
    flushing, healthchecks). The scheduler treats those as a distinct
    partition because the ``org_config`` JOIN won't match.

    ``pipeline_priority`` is bounded to ``MIN_PRIORITY..MAX_PRIORITY``
    (1..10). Higher = sooner.
    """

    org_id: str | None
    workload_type: WorkloadType
    pipeline_priority: int = DEFAULT_PRIORITY

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
            "workload_type": self.workload_type,
            "pipeline_priority": self.pipeline_priority,
        }
