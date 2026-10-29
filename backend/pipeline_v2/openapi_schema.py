"""OpenAPI annotations for the pipeline list and its aggregate. See README.md."""

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from workflow_manager.workflow_v2.list_aggregate_serializers import ListFilterSerializer
from workflow_manager.workflow_v2.list_aggregates import FAILING_LIST_CAP

from pipeline_v2.models import Pipeline
from pipeline_v2.serializers.aggregate import PipelineAggregateSerializer

PIPELINE_LIST_PARAMETERS = [
    OpenApiParameter(
        "type",
        {"type": "string", "enum": list(Pipeline.PipelineType.values)},
        OpenApiParameter.QUERY,
        description="Return only pipelines of this type.",
    ),
    OpenApiParameter(
        "workflow",
        {"type": "string", "format": "uuid"},
        OpenApiParameter.QUERY,
        description="Return only the pipelines of this workflow.",
    ),
    OpenApiParameter(
        "search",
        {"type": "string"},
        OpenApiParameter.QUERY,
        description="Return only pipelines whose name contains this text, "
        "case-insensitively.",
    ),
    OpenApiParameter(
        "pipeline_name",
        {"type": "string"},
        OpenApiParameter.QUERY,
        description="Return only the pipeline with exactly this name.",
    ),
    ListFilterSerializer,
]

PIPELINE_SCHEMA = extend_schema_view(
    list=extend_schema(parameters=PIPELINE_LIST_PARAMETERS),
    aggregate=extend_schema(
        operation_id="aggregate_pipelines",
        summary="Count pipelines by status",
        parameters=PIPELINE_LIST_PARAMETERS,
        responses={200: PipelineAggregateSerializer},
        description=(
            "Counts the pipelines the list returns for the same filters, so "
            f"`total` equals the list's `count`. `failing` holds at most "
            f"{FAILING_LIST_CAP} rows, newest failure first; `failing_count` "
            "counts them all."
        ),
    ),
)
