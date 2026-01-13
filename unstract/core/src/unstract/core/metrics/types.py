"""Metric types and data structures for the metrics module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricType(str, Enum):
    """Type of metric - determines how values are aggregated."""

    COUNTER = "counter"  # Summed values (counts, totals)
    HISTOGRAM = "histogram"  # Distribution metrics (latency, tokens, cost)


class MetricName(str, Enum):
    """Registered metric names.

    All metrics must be registered here to be recorded.
    """

    # Counters - simple incrementing values
    DOCUMENTS_PROCESSED = "documents_processed"
    PAGES_PROCESSED = "pages_processed"
    PROMPT_EXECUTIONS = "prompt_executions"
    LLM_CALLS = "llm_calls"
    CHALLENGES = "challenges"
    SUMMARIZATION_CALLS = "summarization_calls"

    # Histograms - distribution metrics (latency, tokens, cost)
    DEPLOYED_API_REQUESTS = "deployed_api_requests"
    ETL_PIPELINE_EXECUTIONS = "etl_pipeline_executions"
    LLM_USAGE = "llm_usage"


# Mapping of metric names to their types
METRIC_TYPE_MAP: dict[str, MetricType] = {
    # Counters
    MetricName.DOCUMENTS_PROCESSED.value: MetricType.COUNTER,
    MetricName.PAGES_PROCESSED.value: MetricType.COUNTER,
    MetricName.PROMPT_EXECUTIONS.value: MetricType.COUNTER,
    MetricName.LLM_CALLS.value: MetricType.COUNTER,
    MetricName.CHALLENGES.value: MetricType.COUNTER,
    MetricName.SUMMARIZATION_CALLS.value: MetricType.COUNTER,
    # Histograms
    MetricName.DEPLOYED_API_REQUESTS.value: MetricType.HISTOGRAM,
    MetricName.ETL_PIPELINE_EXECUTIONS.value: MetricType.HISTOGRAM,
    MetricName.LLM_USAGE.value: MetricType.HISTOGRAM,
}


@dataclass
class MetricEvent:
    """A single metric event to be recorded.

    Attributes:
        org_id: Organization identifier
        metric_name: Name of the metric (from MetricName enum)
        metric_value: Numeric value (int for counters, float for histograms)
        metric_type: Type of metric (counter or histogram)
        labels: Dimensional labels for filtering/grouping
        project: Project identifier
        tag: Optional tag for categorization
    """

    org_id: str
    metric_name: str
    metric_value: int | float
    metric_type: MetricType
    labels: dict[str, str] = field(default_factory=dict)
    project: str = "default"
    tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "org_id": self.org_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "metric_type": self.metric_type.value,
            "labels": self.labels,
            "project": self.project,
            "tag": self.tag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricEvent":
        """Create from dictionary."""
        return cls(
            org_id=data["org_id"],
            metric_name=data["metric_name"],
            metric_value=data["metric_value"],
            metric_type=MetricType(data["metric_type"]),
            labels=data.get("labels", {}),
            project=data.get("project", "default"),
            tag=data.get("tag"),
        )
