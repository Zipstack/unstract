"""Metric capture helpers for Dashboard Metrics.

This module provides easy-to-use functions for capturing metrics
at key integration points throughout the codebase.

Integration Points:
- API Deployment: Record deployed_api_requests
- ETL Pipeline: Record etl_pipeline_executions
- Document Processing: Record documents_processed, pages_processed
- LLM Calls: Record llm_calls, challenges, summarization_calls
- Prompt Studio: Record prompt_executions

Usage:
    from dashboard_metrics.capture import MetricsCapture

    # In API deployment
    MetricsCapture.record_api_request(org_id, api_name)

    # In document processing
    MetricsCapture.record_document_processed(org_id, pages=5)

    # In LLM call
    MetricsCapture.record_llm_call(org_id, model="gpt-4", cost=0.05)
"""
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Flag to control whether metrics are captured (can be disabled for testing)
METRICS_ENABLED = getattr(settings, "DASHBOARD_METRICS_ENABLED", True)


def _get_metrics_module():
    """Lazy import of the core metrics module.

    Returns None if the module is not available (e.g., in OSS without the core module).
    """
    try:
        from unstract.core.metrics import record, MetricName, MetricType

        return record, MetricName, MetricType
    except ImportError:
        logger.debug("Core metrics module not available")
        return None, None, None


class MetricsCapture:
    """Helper class for capturing metrics at integration points."""

    @staticmethod
    def record_api_request(
        org_id: str,
        api_name: str | None = None,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record an API deployment request.

        Args:
            org_id: Organization ID
            api_name: Name of the API deployment
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if api_name:
            metric_labels["api_name"] = api_name

        return record(
            MetricName.DEPLOYED_API_REQUESTS,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )

    @staticmethod
    def record_etl_execution(
        org_id: str,
        pipeline_name: str | None = None,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record an ETL pipeline execution.

        Args:
            org_id: Organization ID
            pipeline_name: Name of the pipeline
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if pipeline_name:
            metric_labels["pipeline_name"] = pipeline_name

        return record(
            MetricName.ETL_PIPELINE_EXECUTIONS,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )

    @staticmethod
    def record_document_processed(
        org_id: str,
        pages: int = 1,
        file_type: str | None = None,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record document and page processing.

        Args:
            org_id: Organization ID
            pages: Number of pages processed
            file_type: File type (pdf, docx, etc.)
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if file_type:
            metric_labels["file_type"] = file_type

        # Record document
        doc_result = record(
            MetricName.DOCUMENTS_PROCESSED,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )

        # Record pages
        pages_result = record(
            MetricName.PAGES_PROCESSED,
            org_id=org_id,
            value=pages,
            project=project,
            labels=metric_labels,
        )

        return doc_result and pages_result

    @staticmethod
    def record_llm_call(
        org_id: str,
        model: str | None = None,
        cost: float = 0.0,
        tokens: int = 0,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record an LLM API call.

        Args:
            org_id: Organization ID
            model: LLM model name
            cost: Cost in dollars
            tokens: Total tokens used
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if model:
            metric_labels["model"] = model
        if tokens:
            metric_labels["tokens"] = str(tokens)

        # Record the call
        call_result = record(
            MetricName.LLM_CALLS,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )

        # Record usage cost if provided
        if cost > 0:
            record(
                MetricName.LLM_USAGE,
                org_id=org_id,
                value=cost,
                project=project,
                labels=metric_labels,
            )

        return call_result

    @staticmethod
    def record_challenge(
        org_id: str,
        challenge_type: str | None = None,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record an LLM challenge call.

        Args:
            org_id: Organization ID
            challenge_type: Type of challenge
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if challenge_type:
            metric_labels["type"] = challenge_type

        return record(
            MetricName.CHALLENGES,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )

    @staticmethod
    def record_summarization(
        org_id: str,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record a summarization call.

        Args:
            org_id: Organization ID
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        return record(
            MetricName.SUMMARIZATION_CALLS,
            org_id=org_id,
            value=1,
            project=project,
            labels=labels,
        )

    @staticmethod
    def record_prompt_execution(
        org_id: str,
        prompt_name: str | None = None,
        project: str = "default",
        labels: dict[str, Any] | None = None,
    ) -> bool:
        """Record a prompt studio execution.

        Args:
            org_id: Organization ID
            prompt_name: Name of the prompt
            project: Project identifier
            labels: Additional labels

        Returns:
            True if recorded successfully
        """
        if not METRICS_ENABLED:
            return False

        record, MetricName, _ = _get_metrics_module()
        if record is None:
            return False

        metric_labels = labels or {}
        if prompt_name:
            metric_labels["prompt_name"] = prompt_name

        return record(
            MetricName.PROMPT_EXECUTIONS,
            org_id=org_id,
            value=1,
            project=project,
            labels=metric_labels,
        )
