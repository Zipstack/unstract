"""Failed pages broken down by source and by day (PB-T14).

Built from ``MetricsQueryService.failed_file_executions_with_pages``, the same
queryset ``get_failed_pages`` sums for the ``failed_pages`` metric, so the
totals here equal that series for the same range. The response contract is
``contract/attribution-response.schema.json``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from typing import Any

from api_v2.models import APIDeployment
from django.db.models import Sum
from pipeline_v2.models import Pipeline
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.models import Granularity
from dashboard_metrics.services import MetricsQueryService

logger = logging.getLogger(__name__)


class SourceType(StrEnum):
    API_DEPLOYMENT = "api_deployment"
    ETL_PIPELINE = "etl_pipeline"
    TASK_PIPELINE = "task_pipeline"
    # A pipeline of another type (e.g. APP, DEFAULT).
    PIPELINE = "pipeline"
    # Runs with no pipeline: a workflow run by hand.
    WORKFLOW = "workflow"
    # A source whose pipeline, deployment or workflow no longer exists.
    DELETED = "deleted"


_DELETED = (None, SourceType.DELETED)

_PIPELINE_TYPES = {
    Pipeline.PipelineType.ETL: SourceType.ETL_PIPELINE,
    Pipeline.PipelineType.TASK: SourceType.TASK_PIPELINE,
}


def _describe_sources(
    pipeline_ids: set, workflow_ids: set
) -> dict[tuple[str, str], tuple[str | None, str]]:
    """Name and type of each source, keyed by ``(kind, id)``."""
    described: dict[tuple[str, str], tuple[str | None, str]] = {}
    for d in APIDeployment._base_manager.filter(pk__in=pipeline_ids).values(
        "pk", "display_name"
    ):
        described[("pipeline", str(d["pk"]))] = (
            d["display_name"],
            SourceType.API_DEPLOYMENT,
        )
    for p in Pipeline._base_manager.filter(pk__in=pipeline_ids).values(
        "pk", "pipeline_name", "pipeline_type"
    ):
        described[("pipeline", str(p["pk"]))] = (
            p["pipeline_name"],
            _PIPELINE_TYPES.get(p["pipeline_type"], SourceType.PIPELINE),
        )
    for w in Workflow._base_manager.filter(pk__in=workflow_ids).values(
        "pk", "workflow_name"
    ):
        described[("workflow", str(w["pk"]))] = (w["workflow_name"], SourceType.WORKFLOW)
    return described


def failure_attribution(
    organization_id: str, start_date: datetime, end_date: datetime
) -> dict[str, Any]:
    """Failed pages per day and per source for the range.

    A source is the pipeline or API deployment that ran the file, or, for a run
    with no pipeline, its workflow. Sources are ordered by failed pages, most
    first; ``share`` is the source's fraction of the range's failed pages.
    """
    trunc_day = MetricsQueryService._get_trunc_func(Granularity.DAY)
    rows = (
        MetricsQueryService.failed_file_executions_with_pages(
            organization_id, start_date, end_date
        )
        .annotate(period=trunc_day("created_at"))
        .values(
            "period",
            "workflow_execution__pipeline_id",
            "workflow_execution__workflow_id",
        )
        .annotate(value=Sum("pages"))
        .order_by("period")
    )

    per_day: dict[datetime, dict[tuple[str, str], int]] = defaultdict(
        lambda: defaultdict(int)
    )
    per_source: dict[tuple[str, str], int] = defaultdict(int)
    pipeline_ids, workflow_ids = set(), set()
    for row in rows:
        pipeline_id = row["workflow_execution__pipeline_id"]
        if pipeline_id is not None:
            key = ("pipeline", str(pipeline_id))
            pipeline_ids.add(pipeline_id)
        else:
            key = ("workflow", str(row["workflow_execution__workflow_id"]))
            workflow_ids.add(row["workflow_execution__workflow_id"])
        pages = row["value"] or 0
        per_day[row["period"]][key] += pages
        per_source[key] += pages

    described = _describe_sources(pipeline_ids, workflow_ids)
    total = sum(per_source.values())
    unresolved = sorted(per_source.keys() - described.keys())
    if unresolved:
        logger.info(
            "Attribution: %d sources reported as deleted for org %s: %s",
            len(unresolved),
            organization_id,
            unresolved,
        )

    ordered = sorted(per_source.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_failed_pages": total,
        "sources": [
            {
                "id": key[1],
                "name": name,
                "type": source_type.value,
                "failed_pages": pages,
                "share": round(pages / total, 4) if total else 0.0,
            }
            for key, pages in ordered
            for name, source_type in [described.get(key, _DELETED)]
        ],
        "days": [
            {
                "date": period.date().isoformat(),
                "failed_pages": sum(sources.values()),
                "sources": [
                    {"id": key[1], "failed_pages": pages}
                    for key, pages in sorted(
                        sources.items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ],
            }
            for period, sources in sorted(per_day.items())
        ],
    }
