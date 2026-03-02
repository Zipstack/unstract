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
from api_v2.models import APIDeployment
from django.db.models import CharField, Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Cast, Coalesce, TruncDay, TruncHour, TruncWeek
from pipeline_v2.models import Pipeline
from usage_v2.models import Usage
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from dashboard_metrics.models import Granularity
from unstract.core.data_models import ExecutionStatus
from account_v2.models import Organization


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
    def get_pages_processed(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query pages processed from page_usage.

        Sums pages_processed field grouped by time period.

        Note: PageUsage.organization_id stores the Organization's string
        identifier (organization.organization_id), NOT the UUID PK.
        We look up the string identifier from the UUID passed by callers.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range
            granularity: Time granularity (hour, day, week)

        Returns:
            List of dicts with 'period' and 'value' keys
        """
        try:
            org = Organization.objects.get(id=organization_id)
            org_identifier = org.organization_id
        except Organization.DoesNotExist:
            return []

        trunc_func = MetricsQueryService._get_trunc_func(granularity)

        return list(
            PageUsage.objects.filter(
                organization_id=org_identifier,
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Sum("pages_processed"))
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

        Counts usage records where usage_type='llm' grouped by time period.

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
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_challenges(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query challenge calls from usage table.

        Counts usage records where llm_usage_reason='challenge' grouped by time period.

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
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                llm_usage_reason="challenge",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    @staticmethod
    def get_summarization_calls(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query summarization calls from usage table.

        Counts usage records where llm_usage_reason='summarize' grouped by time period.

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
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                llm_usage_reason="summarize",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

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
    def get_llm_usage_cost(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = Granularity.DAY,
    ) -> list[dict[str, Any]]:
        """Query LLM usage cost from usage table.

        Sums cost_in_dollars for LLM usage records grouped by time period.

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
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(value=Sum("cost_in_dollars"))
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
        return {
            "documents_processed": sum(
                r["value"]
                for r in cls.get_documents_processed(
                    organization_id, start_date, end_date
                )
            ),
            "pages_processed": sum(
                r["value"] or 0
                for r in cls.get_pages_processed(organization_id, start_date, end_date)
            ),
            "llm_calls": sum(
                r["value"]
                for r in cls.get_llm_calls(organization_id, start_date, end_date)
            ),
            "challenges": sum(
                r["value"]
                for r in cls.get_challenges(organization_id, start_date, end_date)
            ),
            "summarization_calls": sum(
                r["value"]
                for r in cls.get_summarization_calls(
                    organization_id, start_date, end_date
                )
            ),
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
            "llm_usage": sum(
                r["value"] or 0
                for r in cls.get_llm_usage_cost(organization_id, start_date, end_date)
            ),
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
    def get_workflow_token_usage(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Get per-workflow LLM token usage breakdown.

        Aggregates total_tokens and cost_in_dollars grouped by workflow,
        with workflow name resolved from the Workflow model.

        Args:
            organization_id: Organization UUID string
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with workflow_id, workflow_name, total_tokens,
            total_cost, and call_count, ordered by total_tokens descending.
        """
        from workflow_manager.workflow_v2.models.workflow import Workflow

        # Query Usage grouped by workflow_id
        usage_qs = (
            _get_usage_queryset()
            .filter(
                organization_id=organization_id,
                usage_type="llm",
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            .exclude(Q(workflow_id__isnull=True) | Q(workflow_id=""))
            .values("workflow_id")
            .annotate(
                total_tokens=Sum("total_tokens"),
                total_cost=Sum("cost_in_dollars"),
                call_count=Count("id"),
            )
            .order_by("-total_tokens")
        )

        # Evaluate queryset once to avoid double DB hit
        usage_rows = list(usage_qs)

        # Resolve workflow names using _base_manager to bypass
        # DefaultOrganizationManagerMixin (UserContext is None in Celery tasks)
        workflow_ids = [row["workflow_id"] for row in usage_rows]
        workflow_names = {}
        if workflow_ids:
            workflows = Workflow._base_manager.filter(id__in=workflow_ids).values(
                "id", "workflow_name"
            )
            workflow_names = {str(w["id"]): w["workflow_name"] for w in workflows}

        results = []
        for row in usage_rows:
            wf_id = row["workflow_id"]
            results.append(
                {
                    "workflow_id": str(wf_id),
                    "workflow_name": workflow_names.get(str(wf_id), "Unknown"),
                    "total_tokens": row["total_tokens"] or 0,
                    "total_cost": round(row["total_cost"] or 0, 4),
                    "call_count": row["call_count"] or 0,
                }
            )

        return results
