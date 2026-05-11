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

        # Single materialization with cap+1 sentinel — avoids a separate COUNT
        # query and a second full scan during build.
        rows = list(queryset[: MAX_SYNC_EXPORT_ROWS + 1])
        if len(rows) > MAX_SYNC_EXPORT_ROWS:
            return Response(
                {
                    "error": (
                        f"Too many logs to export (>{MAX_SYNC_EXPORT_ROWS} rows). "
                        "Narrow the filter (e.g. by file or log level) and retry."
                    ),
                    "limit": MAX_SYNC_EXPORT_ROWS,
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        if export_format == "csv":
            body = self._build_csv(rows)
            content_type = "text/csv; charset=utf-8"
        else:
            body = self._build_json(rows)
            content_type = "application/json"

        execution_id = self.kwargs.get("pk")
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"execution_logs_{execution_id}_{timestamp}.{export_format}"

        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _normalize(self, log: ExecutionLog) -> dict:
        """Single source of truth for per-row null-handling and dict-guard.

        Logs warning when `data` is non-dict so silent blank rows in CSV
        still leave a diagnostic trail in operator logs.
        """
        if isinstance(log.data, dict):
            data = log.data
        else:
            if log.data is not None:
                logger.warning(
                    "ExecutionLog %s has non-dict data of type %s; "
                    "emitting blanks in CSV export",
                    log.id,
                    type(log.data).__name__,
                )
            data = {}
        return {
            "id": str(log.id),
            "event_time": log.event_time.isoformat() if log.event_time else None,
            "file_execution_id": (
                str(log.file_execution_id) if log.file_execution_id else None
            ),
            "level": data.get("level", ""),
            "stage": data.get("stage", ""),
            "log_message": data.get("log", ""),
            "raw_data": log.data,
        }

    def _build_csv(self, rows: list[ExecutionLog]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["event_time", "level", "stage", "log", "file_execution_id"])
        for log in rows:
            n = self._normalize(log)
            writer.writerow(
                [
                    n["event_time"] or "",
                    n["level"],
                    n["stage"],
                    n["log_message"],
                    n["file_execution_id"] or "",
                ]
            )
        return output.getvalue()

    def _build_json(self, rows: list[ExecutionLog]) -> str:
        # JSON path passes raw_data through verbatim (faithful to the DB)
        # rather than projecting it to extracted level/stage/log fields.
        entries = [
            {
                "id": n["id"],
                "event_time": n["event_time"],
                "file_execution_id": n["file_execution_id"],
                "data": n["raw_data"],
            }
            for n in (self._normalize(log) for log in rows)
        ]
        return json.dumps(entries)
