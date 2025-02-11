from permissions.permission import IsOwner
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.date import DateRangeKeys, DateRangeSerializer
from utils.pagination import CustomPagination
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer


class PipelineExecutionViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    serializer_class = WorkflowExecutionSerializer
    pagination_class = CustomPagination

    CREATED_AT_FIELD_DESC = "-created_at"

    def get_queryset(self):
        # Get the pipeline_id from the URL path
        pipeline_id = self.kwargs.get("pk")
        queryset = WorkflowExecution.objects.filter(pipeline_id=pipeline_id)

        # Validate start_date and end_date parameters using DateRangeSerializer
        date_range_serializer = DateRangeSerializer(data=self.request.query_params)
        date_range_serializer.is_valid(raise_exception=True)
        start_date = date_range_serializer.validated_data.get(DateRangeKeys.START_DATE)
        end_date = date_range_serializer.validated_data.get(DateRangeKeys.END_DATE)

        if start_date and end_date:
            queryset = queryset.filter(created_at__range=(start_date, end_date))

        queryset = queryset.order_by(self.CREATED_AT_FIELD_DESC)
        return queryset
