import logging
from typing import Any, Optional

from account.custom_exceptions import DuplicateData
from cron_expression_generator.constants import CronKeys
from django.db import IntegrityError
from django.db.models import QuerySet
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from permissions.permission import IsOwner
from pipeline.constants import (
    PipelineConstants,
    PipelineErrors,
    PipelineExecutionKey,
)
from pipeline.constants import PipelineKey as PK
from pipeline.exceptions import MandatoryCronSchedule, MandatoryWorkflowId
from pipeline.manager import PipelineManager
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from pipeline.serializers.crud import PipelineSerializer
from pipeline.serializers.execute import (
    PipelineExecuteSerializer as ExecuteSerializer,
)
from rest_framework import serializers, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from scheduler.helper import SchedulerHelper
from workflow_manager.workflow.constants import (
    WorkflowExecutionKey as WFExecKey,
)
from workflow_manager.workflow.constants import WorkflowKey

logger = logging.getLogger(__name__)


class PipelineViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = Pipeline.objects.all()
    permission_classes = [IsOwner]
    serializer_class = PipelineSerializer

    # For doc strings
    with_log = openapi.Parameter(
        "with_log",
        openapi.IN_QUERY,
        description="To pass workflow execution logs to FE",
        type=openapi.TYPE_BOOLEAN,
        enum=[True, False],
    )

    def get_queryset(self) -> Optional[QuerySet]:
        type = self.request.query_params.get(PipelineConstants.TYPE)
        if type is not None:
            queryset = Pipeline.objects.filter(
                created_by=self.request.user, pipeline_type=type
            )
            return queryset
        elif type is None:
            queryset = Pipeline.objects.filter(created_by=self.request.user)
            return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action == "execute":
            return ExecuteSerializer
        else:
            return PipelineSerializer

    # TODO: Refactor to perform an action with explicit arguments
    # For eg, passing pipeline ID and with_log=False -> executes pipeline
    # For FE however we call the same API twice
    # (first call generates execution ID)
    @swagger_auto_schema(manual_parameters=[with_log])
    def execute(self, request: Request) -> Response:
        # TODO: Use a serializer instead to validate args
        with_log = request.query_params.get(WFExecKey.WITH_LOG)
        serializer: ExecuteSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        execution_id = serializer.validated_data.get("execution_id", None)
        pipeline_id = serializer.validated_data[PK.PIPELINE_ID]

        execution = PipelineManager.execute_pipeline(
            request=request,
            pipeline_id=pipeline_id,
            execution_id=execution_id,
            with_log=with_log,
        )
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(pipeline_id)
        serializer = PipelineSerializer(pipeline)
        response_data = {
            PipelineExecutionKey.PIPELINE: serializer.data,
            PipelineExecutionKey.EXECUTION: execution.data,
        }
        return Response(data=response_data, status=status.HTTP_200_OK)

    def create(self, request: Request) -> Response:
        workflow_id = request.data.get(WorkflowKey.WF_ID)
        cron_string = request.data.get(CronKeys.CRON_STRING)
        # TODO: Remove these checks once ValidationError is handled properly
        if not workflow_id:
            raise MandatoryWorkflowId()
        if not cron_string:
            raise MandatoryCronSchedule()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError:
            raise DuplicateData(
                f"{PipelineErrors.PIPELINE_EXISTS}, "
                f"{PipelineErrors.DUPLICATE_API}"
            )
        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Pipeline) -> None:
        pipeline_to_remove = str(instance.pk)
        super().perform_destroy(instance)
        return SchedulerHelper.remove_job(pipeline_to_remove)

    def partial_update(self, request: Request, pk: Any = None) -> Response:
        pipeline_id = request.data.get("pipeline_id")
        active = request.data.get("active")

        if not pipeline_id:
            return Response(
                {"error": "pipeline_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if active:
                SchedulerHelper.resume_job(pipeline_id)
            else:
                SchedulerHelper.pause_job(pipeline_id)
        except Exception as e:
            logger.error(f"Failed to update pipeline status: {e}")
            return Response(
                {"error": "Failed to update pipeline status"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "status": "success",
                "message": f"Pipeline {pipeline_id} status updated",
            },
            status=status.HTTP_200_OK,
        )
