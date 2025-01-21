import logging

from django.db.models.query import QuerySet
from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.pagination import CustomPagination
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.serializers import WorkflowExecutionLogSerializer

logger = logging.getLogger(__name__)


class WorkflowExecutionLogViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    allowed_versions = ["v1", "v2"]
    serializer_class = WorkflowExecutionLogSerializer
    pagination_class = CustomPagination

    EVENT_TIME_FIELD_ASC = "event_time"

    def get_queryset(self) -> QuerySet:
        # Get the execution_id:pk from the URL path
        execution_id = self.kwargs.get("pk")
        filter_param = {"execution_id": execution_id}

        # In v2, allow filtering by file_execution_id and log level
        if self.request.version == "v2":
            file_execution_id = self.request.query_params.get("file_execution_id")
            filter_param["file_execution_id"] = file_execution_id

            log_level = self.request.query_params.get("log_level")
            if log_level:
                filter_param["data__level"] = log_level.upper()

        queryset = ExecutionLog.objects.filter(**filter_param).order_by(
            self.EVENT_TIME_FIELD_ASC
        )
        return queryset
