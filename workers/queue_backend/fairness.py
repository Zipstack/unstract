"""Workflow-execution fairness key.

Attached to dispatches that start a workflow execution. Non-workflow
worker tasks (notifications, callbacks, healthchecks) pass
``fairness=None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypedDict


class FairnessPayload(TypedDict):
    """Serialised :class:`FairnessKey` (``to_dict()`` / wire shape).

    Shared so producers and the PG ``TaskPayload`` wire contract agree on
    the exact sub-shape instead of a loose ``dict[str, Any]``.
    """

    org_id: str | None
    workload_type: str
    pipeline_priority: int


class WorkloadType(StrEnum):
    """Workflow execution type. Labs L2 check is binary api-vs-not."""

    API = "api"
    NON_API = "non_api"


# pipeline_priority bounds per labs schema (1..10, higher = sooner).
MIN_PRIORITY: Final[int] = 1
MAX_PRIORITY: Final[int] = 10
DEFAULT_PRIORITY: Final[int] = 5

# Header (not kwarg) so task-body signatures without **kwargs aren't broken.
FAIRNESS_HEADER_NAME: Final[str] = "x-fairness-key"


@dataclass(frozen=True)
class FairnessKey:
    """Routing metadata for a workflow-execution dispatch.

    ``org_id=None`` is valid for cross-org tasks — the scheduler's
    ``org_config`` JOIN simply doesn't match.
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

    def to_dict(self) -> FairnessPayload:
        return FairnessPayload(
            org_id=self.org_id,
            workload_type=self.workload_type.value,
            pipeline_priority=self.pipeline_priority,
        )

    def as_header(self) -> dict[str, dict[str, str | int | None]]:
        """Celery ``send_task(headers=...)`` payload.

        Shape: ``{FAIRNESS_HEADER_NAME: self.to_dict()}``.
        """
        return {FAIRNESS_HEADER_NAME: self.to_dict()}
