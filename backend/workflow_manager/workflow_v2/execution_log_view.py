import csv
import io
import json
import logging

from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import HttpResponse
from django.utils import timezone
from permissions.permission import IsOwner
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.pagination import CustomPagination

from workflow_manager.workflow_v2.filters import ExecutionLogFilter
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.serializers import WorkflowExecutionLogSerializer

logger = logging.getLogger(__name__)

# Cap on synchronous export size. Above this, callers should narrow the
# filter (file_execution_id, log_level) — async deployment-wide export
# is intentionally a separate, future feature.
MAX_SYNC_EXPORT_ROWS = 50_000


class WorkflowExecutionLogViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = WorkflowExecutionLogSerializer
    pagination_class = CustomPagination
    ordering_fields = ["event_time"]
    ordering = ["event_time"]
    filterset_class = ExecutionLogFilter

    def get_queryset(self) -> QuerySet:
        execution_id = self.kwargs.get("pk")

        # Query by execution_id for backward compatibility
        # Remove filter after execution_id is removed
        return ExecutionLog.objects.filter(
            Q(wf_execution_id=execution_id) | Q(execution_id=execution_id)
        )

    def export(self, request, *args, **kwargs):
        """Export logs for a single workflow execution as CSV or JSON.

        Honors the same filters as the list endpoint (file_execution_id,
        log_level). Returns 413 if the result set exceeds the sync cap so
        the client can prompt the user to narrow their filter.
        """
        # NOTE: do not name this query param `format` — DRF reserves it for
        # content negotiation and will 404 if no renderer matches the value.
        export_format = request.query_params.get("file_format", "json").lower()
        if export_format not in ("json", "csv"):
            return Response(
                {"error": "file_format must be one of: json, csv"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = (
            self.filter_queryset(self.get_queryset())
            .order_by("event_time")
            .only("id", "event_time", "data", "file_execution_id")
        )

        row_count = queryset.count()
        if row_count > MAX_SYNC_EXPORT_ROWS:
            return Response(
                {
                    "error": (
                        f"Too many logs to export ({row_count} rows). "
                        f"Limit is {MAX_SYNC_EXPORT_ROWS}. "
                        "Narrow the filter (e.g. by file or log level) and retry."
                    ),
                    "row_count": row_count,
                    "limit": MAX_SYNC_EXPORT_ROWS,
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        if export_format == "csv":
            body = self._build_csv(queryset)
            content_type = "text/csv"
        else:
            body = self._build_json(queryset)
            content_type = "application/json"

        execution_id = self.kwargs.get("pk")
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"execution_logs_{execution_id}_{timestamp}.{export_format}"

        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _build_csv(self, queryset: QuerySet) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["event_time", "level", "stage", "log", "file_execution_id"])
        for log in queryset:
            data = log.data if isinstance(log.data, dict) else {}
            writer.writerow(
                [
                    log.event_time.isoformat() if log.event_time else "",
                    data.get("level", ""),
                    data.get("stage", ""),
                    data.get("log", ""),
                    str(log.file_execution_id) if log.file_execution_id else "",
                ]
            )
        return output.getvalue()

    def _build_json(self, queryset: QuerySet) -> str:
        entries = [
            {
                "id": str(log.id),
                "event_time": log.event_time.isoformat() if log.event_time else None,
                "file_execution_id": (
                    str(log.file_execution_id) if log.file_execution_id else None
                ),
                "data": log.data,
            }
            for log in queryset
        ]
        return json.dumps(entries)
