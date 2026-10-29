"""Stuck-execution count and abort. See ../README.md for the contract."""

from drf_spectacular.utils import OpenApiExample, extend_schema
from drf_standardized_errors.openapi_serializers import (
    ErrorResponse403Serializer,
    ValidationErrorResponseSerializer,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from workflow_manager.execution.abort import abort_executions
from workflow_manager.execution.serializer.stuck_abort import (
    ExecutionAbortRequestSerializer,
    ExecutionAbortResponseSerializer,
    StuckExecutionCountSerializer,
)
from workflow_manager.execution.stuck import count_stuck
from workflow_manager.workflow_v2.models import WorkflowExecution

_TAGS = ["execution"]


class StuckExecutionCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="execution_stuck_count",
        tags=_TAGS,
        description="Stuck executions visible to the caller, per entity.",
        responses={200: StuckExecutionCountSerializer, 403: ErrorResponse403Serializer},
        examples=[
            OpenApiExample(
                "Counts",
                value={
                    "threshold_seconds": 9000,
                    "total": 3,
                    "counts": {"API": 1, "ETL": 2, "TASK": 0, "WF": 0},
                },
                response_only=True,
            )
        ],
    )
    def get(self, request: Request) -> Response:
        report = count_stuck(WorkflowExecution.objects.for_user(request.user))
        return Response(StuckExecutionCountSerializer(report).data)


class ExecutionAbortView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="execution_abort",
        tags=_TAGS,
        description=(
            "Stop running executions. Only the owner or an org admin may abort; "
            "every id gets its own outcome in a 200."
        ),
        request=ExecutionAbortRequestSerializer,
        responses={
            200: ExecutionAbortResponseSerializer,
            400: ValidationErrorResponseSerializer,
            403: ErrorResponse403Serializer,
        },
    )
    def post(self, request: Request) -> Response:
        body = ExecutionAbortRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        report = abort_executions(request, body.validated_data["ids"])
        return Response(ExecutionAbortResponseSerializer(report).data)
