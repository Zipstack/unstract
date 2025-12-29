"""Services for querying metrics from existing tables.

This module provides the MetricsQueryService class which queries metrics
directly from source tables (usage, page_usage, workflow_execution, etc.)
instead of relying on the event_metrics_hourly aggregation table.

This enables immediate metrics availability without waiting for real-time
capture integration to be completed.
"""

from datetime import datetime
from typing import Any

from django.db.models import Count, OuterRef, Subquery, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncWeek

from account_usage.models import PageUsage
from api_v2.models import APIDeployment
from pipeline_v2.models import Pipeline
from usage_v2.models import Usage
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


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
            "hour": TruncHour,
            "day": TruncDay,
            "week": TruncWeek,
        }
        return trunc_map.get(granularity, TruncDay)

    @staticmethod
    def get_documents_processed(
        organization_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "day",
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
                status="COMPLETED",
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
        granularity: str = "day",
    ) -> list[dict[str, Any]]:
        """Query pages processed from page_usage.

        Sums pages_processed field grouped by time period.

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
            PageUsage.objects.filter(
                organization_id=organization_id,
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
        granularity: str = "day",
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
            Usage.objects.filter(
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
        granularity: str = "day",
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
            Usage.objects.filter(
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
        granularity: str = "day",
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
            Usage.objects.filter(
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
        granularity: str = "day",
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

        # Use subquery to avoid materializing ID list (N+1 optimization)
        api_subquery = APIDeployment.objects.filter(
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
        granularity: str = "day",
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

        # Use subquery to avoid materializing ID list (N+1 optimization)
        pipeline_subquery = Pipeline.objects.filter(
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
        granularity: str = "day",
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
            Usage.objects.filter(
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
        granularity: str = "day",
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
                for r in cls.get_documents_processed(organization_id, start_date, end_date)
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
                for r in cls.get_prompt_executions(
                    organization_id, start_date, end_date
                )
            ),
        }
