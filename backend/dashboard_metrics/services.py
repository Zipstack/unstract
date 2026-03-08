"""Services for querying metrics from existing tables.

This module provides the MetricsQueryService class which queries metrics
directly from source tables (usage, page_usage, workflow_execution, etc.)
and aggregates them into event_metrics_hourly/daily/monthly tables.

Note: Uses _base_manager for models with DefaultOrganizationManagerMixin
to bypass the UserContext filter when running from Celery tasks.
"""

from datetime import datetime
from typing import Any

from account_usage.models import PageUsage
from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.db.models import CharField, Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Cast, Coalesce, TruncDay, TruncHour, TruncWeek
from pipeline_v2.models import Pipeline
from usage_v2.models import Usage
from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.models import Granularity
from unstract.core.data_models import ExecutionStatus


def _get_hitl_queue_model():
    """Get HITLQueue model if available (cloud-only).

    Returns None on OSS where manual_review_v2 is not installed.
    """
    try:
        from pluggable_apps.manual_review_v2.models import HITLQueue

        return HITLQueue
    except ImportError:
        return None


def _get_usage_queryset():
    """Get Usage queryset bypassing the organization context filter.

    Usage model uses DefaultOrganizationManagerMixin which filters by
    UserContext.get_organization(). This returns None in Celery tasks,
    causing queries to return empty results. Use _base_manager instead.
    """
    return Usage._base_manager.all()


class MetricsQueryService:
    """Service for querying metrics from source tables.

    This service provides methods to query each metric type from its
    respective source table, with support for date filtering and
    time-based aggregation (hourly, daily, weekly).

    Metrics available:
    - documents_processed: from workflow_file_execution
    - pages_processed: from page_usage
    - llm_calls: from usage (type=llm)
    - challenges: from usage (reason=challenge)
    - summarization_calls: from usage (reason=summarize)
    - deployed_api_requests: from workflow_execution + api_deployment
    - etl_pipeline_executions: from workflow_execution + pipeline
    - llm_usage: from usage (cost_in_dollars)
    - prompt_executions: from workflow_execution
    """

    @staticmethod
    def _get_trunc_func(granularity: str):
        """Get the appropriate truncation function for the granularity."""
        trunc_map = {
            Granularity.HOUR: TruncHour,
            Granularity.DAY: TruncDay,
            Granularity.WEEK: TruncWeek,
        }
        return trunc_map.get(granularity, TruncDay)

    @staticmethod
    def get_documents_processed(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query documents processed from workflow_file_execution.

        Counts completed file executions grouped by time period.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            WorkflowFileExecution.objects.filter(
                workflow_execution__workflow__organization_id=organization_id,
                status=ExecutionStatus.COMPLETED,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def _resolve_org_identifier(
        organization_id: str, org_identifier: str | None = None
    ) -> str | None:
        """Resolve PageUsage's string org identifier from UUID PK.

        PageUsage.organization_id stores Organization.organization_id (a string
        like "org_abc123"), not the UUID PK used everywhere else. This helper
        resolves the string identifier, accepting a pre-resolved value to avoid
        redundant DB lookups when called in a loop.

        Args:
            organization_id: Organization UUID string (PK)
            org_identifier: Pre-resolved string identifier (skips DB lookup)

        Returns:
            Organization string identifier, or None if org not found
        """
        if org_identifier:
            return org_identifier
        try:
            org = Organization.objects.get(id=organization_id)
            return org.organization_id
        except Organization.DoesNotExist:
            return None

    @staticmethod
    def get_pages_processed(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
        org_identifier: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query pages processed from page_usage.

        Sums pages_processed field grouped by time period.

        Note: PageUsage.organization_id stores the Organization's string
        identifier (organization.organization_id), NOT the UUID PK.
        Pass org_identifier to avoid a DB lookup per call.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)
            org_identifier: Pre-resolved Organization.organization_id string.
                If None, will be looked up from organization_id.

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        resolved = MetricsQueryService._resolve_org_identifier(
            organization_id, org_identifier
        )
        if not resolved:
            return []

        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            PageUsage.objects.filter(
                organization_id=resolved,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Sum("pages_processed"))
            .order_by("period")
        )

    @staticmethod
    def get_llm_metrics_combined(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query all LLM metrics from usage table in a single query.

        Uses conditional aggregation to compute llm_calls, challenges,
        summarization_calls, and llm_usage (cost) in one DB round-trip
        instead of four separate queries.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period', 'llm_calls', 'challenges',
            'summarization_calls', and 'llm_usage' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(
                llm_calls=Count("id"),
                challenges=Count("id", filter=Q(llm_usage_reason="challenge")),
                summarization_calls=Count("id", filter=Q(llm_usage_reason="summarize")),
                llm_usage=Sum("cost_in_dollars"),
            )
            .order_by("period")
        )

    @staticmethod
    def get_llm_calls(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query LLM calls from usage table.

        Thin wrapper for views/backfill that need a single metric.
        For batch aggregation, use get_llm_metrics_combined() instead.
        """
        return [
            {"period": r["period"], "value": r["llm_calls"]}
            for r in MetricsQueryService.get_llm_metrics_combined(
                organization_id, start_date, end_date, granularity
            )
        ]

    @staticmethod
    def get_challenges(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query challenge calls from usage table.

        Thin wrapper for views/backfill that need a single metric.
        For batch aggregation, use get_llm_metrics_combined() instead.
        """
        return [
            {"period": r["period"], "value": r["challenges"]}
            for r in MetricsQueryService.get_llm_metrics_combined(
                organization_id, start_date, end_date, granularity
            )
        ]

    @staticmethod
    def get_summarization_calls(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query summarization calls from usage table.

        Thin wrapper for views/backfill that need a single metric.
        For batch aggregation, use get_llm_metrics_combined() instead.
        """
        return [
            {"period": r["period"], "value": r["summarization_calls"]}
            for r in MetricsQueryService.get_llm_metrics_combined(
                organization_id, start_date, end_date, granularity
            )
        ]

    @staticmethod
    def get_llm_usage_cost(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query LLM usage cost from usage table.

        Thin wrapper for views/backfill that need a single metric.
        For batch aggregation, use get_llm_metrics_combined() instead.
        """
        return [
            {"period": r["period"], "value": r["llm_usage"]}
            for r in MetricsQueryService.get_llm_metrics_combined(
                organization_id, start_date, end_date, granularity
            )
        ]

    @staticmethod
    def get_deployed_api_requests(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query API deployment requests from workflow_execution.

        Counts workflow executions where pipeline_id matches an API deployment
        for the organization, grouped by time period.

        Uses subquery to avoid N+1 query pattern.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        # Use _base_manager to bypass DefaultOrganizationManagerMixin
        # (UserContext is None in Celery tasks)
        api_subquery = APIDeployment._base_manager.filter(
            organization_id=organization_id
        ).values("id")

        return list(
            WorkflowExecution.objects.filter(
                pipeline_id__in=Subquery(api_subquery),
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_etl_pipeline_executions(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query ETL pipeline executions from workflow_execution.

        Counts workflow executions where pipeline_id matches an ETL pipeline
        for the organization, grouped by time period.

        Uses subquery to avoid N+1 query pattern.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        # Use _base_manager to bypass DefaultOrganizationManagerMixin
        # (UserContext is None in Celery tasks)
        pipeline_subquery = Pipeline._base_manager.filter(
            organization_id=organization_id,
            pipeline_type="ETL",
        ).values("id")

        return list(
            WorkflowExecution.objects.filter(
                pipeline_id__in=Subquery(pipeline_subquery),
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_prompt_executions(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query prompt executions from workflow_execution.

        Counts all workflow executions for the organization grouped by time period.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            WorkflowExecution.objects.filter(
                workflow__organization_id=organization_id,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_failed_pages(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query failed pages from workflow_file_execution + page_usage.

        Sums pages_processed for file executions with status='ERROR',
        grouped by time period based on when the failure occurred.

        Note: Unlike get_pages_processed, this does NOT need org_identifier
        because it joins through WorkflowFileExecution -> WorkflowExecution ->
        Workflow -> Organization (UUID FK), not through PageUsage.organization_id.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        # Subquery: get pages for each file execution from page_usage
        # Join on: page_usage.run_id = workflow_file_execution.id::text
        pages_subquery = (
            PageUsage.objects.filter(run_id=Cast(OuterRef("id"), CharField()))
            .values("run_id")
            .annotate(total=Sum("pages_processed"))
            .values("total")[:1]
        )

        # Main query: failed executions with their pages, grouped by period
        return list(
            WorkflowFileExecution.objects.filter(
                workflow_execution__workflow__organization_id=organization_id,
                status=ExecutionStatus.ERROR,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(
                pages=Coalesce(Subquery(pages_subquery), 0),
                period=trunc_func("created_at"),
            )
            .values("period")
            .annotate(value=Sum("pages"))
            .order_by("period")
        )

    @staticmethod
    def get_hitl_reviews(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query HITL review counts from manual_review_v2.

        Counts all HITLQueue records created in the date range,
        regardless of their current state.

        Returns empty list on OSS where manual_review_v2 is not installed.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        HITLQueue = _get_hitl_queue_model()
        if HITLQueue is None:
            return []

        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            HITLQueue._base_manager.filter(
                organization_id=organization_id,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_hitl_completions(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query completed HITL reviews from manual_review_v2.

        Counts HITLQueue records with state='approved' that were approved
        within the date range (using approved_at timestamp).

        Returns empty list on OSS where manual_review_v2 is not installed.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        HITLQueue = _get_hitl_queue_model()
        if HITLQueue is None:
            return []

        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            HITLQueue._base_manager.filter(
                organization_id=organization_id,
                state=HITLQueue.State.APPROVED,
                approved_at__gte=start_date,
                approved_at__lte=end_date,
            )
            .annotate(period=trunc_func("approved_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @classmethod
    def get_all_metrics_summary(
        cls,
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, float]:
        """Get summary totals for all metrics.

        Aggregates all metric types for the given date range.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dict mapping metric name to total value
        """
        # Resolve org identifier once for PageUsage queries
        org_identifier = cls._resolve_org_identifier(organization_id)

        # Combined LLM metrics (1 query instead of 4)
        llm_combined = cls.get_llm_metrics_combined(organization_id, start_date, end_date)
        llm_calls_total = sum(r["llm_calls"] for r in llm_combined)
        challenges_total = sum(r["challenges"] for r in llm_combined)
        summarization_total = sum(r["summarization_calls"] for r in llm_combined)
        llm_usage_total = sum(r["llm_usage"] or 0 for r in llm_combined)

        return {
            "documents_processed": sum(
                r["value"]
                for r in cls.get_documents_processed(
                    organization_id, start_date, end_date
                )
            ),
            "pages_processed": sum(
                r["value"] or 0
                for r in cls.get_pages_processed(
                    organization_id,
                    start_date,
                    end_date,
                    org_identifier=org_identifier,
                )
            ),
            "llm_calls": llm_calls_total,
            "challenges": challenges_total,
            "summarization_calls": summarization_total,
            "deployed_api_requests": sum(
                r["value"]
                for r in cls.get_deployed_api_requests(
                    organization_id, start_date, end_date
                )
            ),
            "etl_pipeline_executions": sum(
                r["value"]
                for r in cls.get_etl_pipeline_executions(
                    organization_id, start_date, end_date
                )
            ),
            "llm_usage": llm_usage_total,
            "prompt_executions": sum(
                r["value"]
                for r in cls.get_prompt_executions(organization_id, start_date, end_date)
            ),
            "failed_pages": sum(
                r["value"] or 0
                for r in cls.get_failed_pages(organization_id, start_date, end_date)
            ),
            "hitl_reviews": sum(
                r["value"]
                for r in cls.get_hitl_reviews(organization_id, start_date, end_date)
            ),
            "hitl_completions": sum(
                r["value"]
                for r in cls.get_hitl_completions(organization_id, start_date, end_date)
            ),
        }

    @staticmethod
    def get_recent_activity(
        organization_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent processing activity across all execution types.

        Returns recent file executions with type differentiation:
        - etl: pipeline_id matches ETL Pipeline
        - api: pipeline_id matches APIDeployment
        - workflow: pipeline_id is null (manual workflow/prompt studio)

        Args:
            organization_id: Organization UUID string
            limit: Maximum number of records to return

        Returns:
            List of dicts with execution details including type
        """
        # Use _base_manager to bypass DefaultOrganizationManagerMixin
        # (UserContext is None in Celery tasks)
        etl_pipeline_ids = set(
            Pipeline._base_manager.filter(
                organization_id=organization_id,
                pipeline_type="ETL",
            ).values_list("id", flat=True)
        )

        api_deployment_ids = set(
            APIDeployment._base_manager.filter(
                organization_id=organization_id,
            ).values_list("id", flat=True)
        )

        # Query recent file executions with related data
        recent = (
            WorkflowFileExecution.objects.filter(
                workflow_execution__workflow__organization_id=organization_id,
            )
            .select_related(
                "workflow_execution",
                "workflow_execution__workflow",
            )
            .order_by("-created_at")[:limit]
        )

        results = []
        for execution in recent:
            pipeline_id = execution.workflow_execution.pipeline_id

            # Determine execution type based on pipeline_id
            if pipeline_id and pipeline_id in etl_pipeline_ids:
                exec_type = "etl"
            elif pipeline_id and pipeline_id in api_deployment_ids:
                exec_type = "api"
            else:
                exec_type = "workflow"

            results.append(
                {
                    "id": str(execution.id),
                    "execution_id": str(execution.workflow_execution.id),
                    "type": exec_type,
                    "file_name": execution.file_name,
                    "status": execution.status,
                    "workflow_name": execution.workflow_execution.workflow.workflow_name,
                    "created_at": execution.created_at.isoformat(),
                    "execution_time": execution.execution_time,
                }
            )

        # Batch query: get aggregated token/cost per file execution
        file_exec_ids = [r["id"] for r in results]
        usage_agg: dict[str, dict[str, Any]] = {}
        if file_exec_ids:
            agg_qs = (
                _get_usage_queryset()
                .filter(run_id__in=file_exec_ids)
                .values("run_id")
                .annotate(
                    total_tokens=Sum("total_tokens"),
                    cost=Sum("cost_in_dollars"),
                )
            )
            usage_agg = {
                str(row["run_id"]): {
                    "total_tokens": row["total_tokens"] or 0,
                    "cost": round(row["cost"] or 0, 4),
                }
                for row in agg_qs
            }

        # Enrich results with LLM usage data
        for r in results:
            agg = usage_agg.get(r["id"], {})
            r["total_tokens"] = agg.get("total_tokens", 0)
            r["cost"] = agg.get("cost", 0)

        return results

    @staticmethod
    def _get_deployment_names(
        deployment_type: str,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Get deployment ID->name mapping and execution filter for a type.

        Uses the default model manager which auto-filters by the current
        user's organization via DefaultOrganizationManagerMixin.

        Returns:
            (dep_names, exec_filter) or ({}, {}) if type is invalid.
        """
        if deployment_type == ExecutionEntity.API.value:
            dep_list = list(APIDeployment.objects.all().values_list("id", "display_name"))
            exec_filter = {"pipeline_id__in": [d[0] for d in dep_list]}
        elif deployment_type in (
            ExecutionEntity.ETL.value,
            ExecutionEntity.TASK.value,
        ):
            dep_list = list(
                Pipeline.objects.filter(
                    pipeline_type=deployment_type,
                ).values_list("id", "pipeline_name")
            )
            exec_filter = {"pipeline_id__in": [d[0] for d in dep_list]}
        elif deployment_type == ExecutionEntity.WORKFLOW.value:
            dep_list = list(Workflow.objects.all().values_list("id", "workflow_name"))
            exec_filter = {
                "pipeline_id__isnull": True,
                "workflow_id__in": [d[0] for d in dep_list],
            }
        else:
            return {}, {}

        dep_names = {str(dep_id): name for dep_id, name in dep_list}
        return dep_names, exec_filter

    @staticmethod
    def _build_exec_stats(
        exec_rows: list[dict], dep_field: str
    ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        """Build exec->deployment mapping and per-deployment stats."""
        exec_to_dep: dict[str, str] = {}
        dep_exec_stats: dict[str, dict[str, Any]] = {}
        status_counters = {
            ExecutionStatus.COMPLETED.value: "completed",
            ExecutionStatus.ERROR.value: "failed",
        }

        def _default_stats() -> dict[str, Any]:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "first_execution_at": None,
                "last_execution_at": None,
            }

        for e in exec_rows:
            exec_id = str(e["id"])
            dep_id = str(e[dep_field])
            exec_to_dep[exec_id] = dep_id

            stats = dep_exec_stats.setdefault(dep_id, _default_stats())
            stats["total"] += 1

            counter_key = status_counters.get(str(e["status"] or ""))
            if counter_key:
                stats[counter_key] += 1

            ts = e["created_at"]
            if not ts:
                continue
            first = stats["first_execution_at"]
            last = stats["last_execution_at"]
            stats["first_execution_at"] = ts if first is None else min(first, ts)
            stats["last_execution_at"] = ts if last is None else max(last, ts)

        return exec_to_dep, dep_exec_stats

    @staticmethod
    def _get_pages_by_deployment(
        exec_rows: list[dict], exec_to_dep: dict[str, str]
    ) -> dict[str, int]:
        """Query pages processed, aggregated by deployment.

        Two queries:
        1. WorkflowFileExecution → map file_exec_id to workflow_execution_id
        2. PageUsage → aggregate pages by file_exec_id, then map to deployment
        """
        exec_ids = [e["id"] for e in exec_rows]
        if not exec_ids:
            return {}

        # Map file_execution_id → workflow_execution_id
        file_exec_map: dict[str, str] = {}
        for fid, weid in WorkflowFileExecution.objects.filter(
            workflow_execution_id__in=exec_ids,
        ).values_list("id", "workflow_execution_id"):
            file_exec_map[str(fid)] = str(weid)

        if not file_exec_map:
            return {}

        page_rows = (
            PageUsage.objects.filter(
                run_id__in=list(file_exec_map.keys()),
            )
            .values("run_id")
            .annotate(pages=Sum("pages_processed"))
        )

        dep_pages: dict[str, int] = {}
        for row in page_rows:
            we_id = file_exec_map.get(row["run_id"])
            dep_id = exec_to_dep.get(we_id) if we_id else None
            if dep_id:
                dep_pages[dep_id] = dep_pages.get(dep_id, 0) + (row["pages"] or 0)
        return dep_pages

    @staticmethod
    def _aggregate_usage_by_deployment(
        usage_rows: list[dict], exec_to_dep: dict[str, str]
    ) -> dict[str, dict[str, Any]]:
        """Aggregate LLM token usage by deployment."""
        dep_agg: dict[str, dict[str, Any]] = {}
        for row in usage_rows:
            dep_id = exec_to_dep.get(row["execution_id"])
            if not dep_id:
                continue
            if dep_id not in dep_agg:
                dep_agg[dep_id] = {
                    "total_tokens": 0,
                    "total_cost": 0,
                    "call_count": 0,
                }
            agg = dep_agg[dep_id]
            agg["total_tokens"] += row["total_tokens"] or 0
            agg["total_cost"] += row["total_cost"] or 0
            agg["call_count"] += row["call_count"] or 0
        return dep_agg

    @staticmethod
    def get_deployment_usage(
        deployment_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Get LLM usage grouped by deployment.

        Joins workflow_execution -> deployment table -> usage to aggregate
        token usage per deployment. Supports 4 deployment types:
        - API: workflow_execution.pipeline_id -> api_deployment
        - ETL: workflow_execution.pipeline_id -> pipeline (type=ETL)
        - TASK: workflow_execution.pipeline_id -> pipeline (type=TASK)
        - WF: workflow_execution with no pipeline (direct workflow runs)

        Also includes execution status counts, pages processed (via
        page_usage), and execution date range per deployment.

        Args:
            deployment_type: One of API, ETL, TASK, WF
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts ordered by total_tokens descending.
        """
        # Step 1: Get deployment names and execution filter
        dep_names, exec_filter = MetricsQueryService._get_deployment_names(
            deployment_type
        )
        if not dep_names:
            return []

        # Step 2: Get executions with status and timestamp
        dep_field = (
            "workflow_id"
            if deployment_type == ExecutionEntity.WORKFLOW.value
            else "pipeline_id"
        )
        # exec_filter already scopes to org-owned deployment IDs
        exec_rows = list(
            WorkflowExecution.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date,
                **exec_filter,
            ).values("id", dep_field, "status", "created_at")
        )
        if not exec_rows:
            return []

        # Step 3: Build exec->deployment mapping and stats
        exec_to_dep, dep_exec_stats = MetricsQueryService._build_exec_stats(
            exec_rows, dep_field
        )

        # Step 4: Query LLM usage
        # Use _get_usage_queryset() to bypass DefaultOrganizationManagerMixin
        # which auto-filters by UserContext and can return empty results.
        usage_rows = list(
            _get_usage_queryset()
            .filter(
                execution_id__in=list(exec_to_dep.keys()),
                usage_type="llm",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .values("execution_id")
            .annotate(
                total_tokens=Sum("total_tokens"),
                total_cost=Sum("cost_in_dollars"),
                call_count=Count("id"),
            )
        )

        # Step 5: Query pages and aggregate usage
        dep_pages = MetricsQueryService._get_pages_by_deployment(exec_rows, exec_to_dep)
        dep_agg = MetricsQueryService._aggregate_usage_by_deployment(
            usage_rows, exec_to_dep
        )

        # Ensure all deployments with executions appear in results
        empty_agg = {"total_tokens": 0, "total_cost": 0, "call_count": 0}
        for dep_id in dep_exec_stats:
            dep_agg.setdefault(dep_id, dict(empty_agg))

        # Step 6: Build results sorted by total_tokens descending
        results = []
        for dep_id, agg in sorted(
            dep_agg.items(), key=lambda x: x[1]["total_tokens"], reverse=True
        ):
            stats = dep_exec_stats.get(dep_id, {})
            results.append(
                {
                    "deployment_id": dep_id,
                    "deployment_name": dep_names.get(dep_id, "Unknown"),
                    "total_tokens": agg["total_tokens"],
                    "total_cost": round(agg["total_cost"], 4),
                    "call_count": agg["call_count"],
                    "execution_count": stats.get("total", 0),
                    "completed_executions": stats.get("completed", 0),
                    "failed_executions": stats.get("failed", 0),
                    "total_pages_processed": dep_pages.get(dep_id, 0),
                    "first_execution_at": (
                        stats["first_execution_at"].isoformat()
                        if stats.get("first_execution_at")
                        else None
                    ),
                    "last_execution_at": (
                        stats["last_execution_at"].isoformat()
                        if stats.get("last_execution_at")
                        else None
                    ),
                }
            )

        return results
