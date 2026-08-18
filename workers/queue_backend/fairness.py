"""Workflow-execution fairness key.

Attached to dispatches that start a workflow execution. Non-workflow
worker tasks (notifications, callbacks, healthchecks) pass
``fairness=None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# The wire shape, the WorkloadType enum, and the priority bounds now live in
# unstract.core (shared backend↔worker single source of truth); re-exported here
# so existing ``from ..fairness import FairnessPayload/WorkloadType/...`` imports
# keep working and the backend producer references the same definitions.
from unstract.core.data_models import (
    FAIRNESS_DEFAULT_PRIORITY as DEFAULT_PRIORITY,
)
from unstract.core.data_models import (
    FAIRNESS_MAX_PRIORITY as MAX_PRIORITY,
)
from unstract.core.data_models import (
    FAIRNESS_MIN_PRIORITY as MIN_PRIORITY,
)
from unstract.core.data_models import (
    FairnessPayload,
    WorkloadType,
)

__all__ = [
    "DEFAULT_PRIORITY",
    "MAX_PRIORITY",
    "MIN_PRIORITY",
    "FairnessPayload",
    "WorkloadType",
]

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
