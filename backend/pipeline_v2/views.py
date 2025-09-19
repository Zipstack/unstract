import json
import logging

from account_v2.custom_exceptions import DuplicateData
from api_v2.exceptions import NoActiveAPIKeyError
from api_v2.key_helper import KeyHelper
from api_v2.postman_collection.dto import PostmanCollection
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpResponse
from permissions.permission import IsOwner, IsOwnerOrSharedUser
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from scheduler.helper import SchedulerHelper

from pipeline_v2.constants import (
    PipelineConstants,
    PipelineErrors,
    PipelineExecutionKey,
)
from pipeline_v2.constants import PipelineKey as PK
from pipeline_v2.manager import PipelineManager
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from pipeline_v2.serializers.crud import PipelineSerializer
from pipeline_v2.serializers.execute import (
    PipelineExecuteSerializer as ExecuteSerializer,
)
from pipeline_v2.serializers.sharing import SharedUserListSerializer

logger = logging.getLogger(__name__)


class PipelineViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = Pipeline.objects.all()
    permission_classes = [IsOwnerOrSharedUser]
    serializer_class = PipelineSerializer

    def get_queryset(self) -> QuerySet:
        # Use for_user manager method to include shared pipelines
        queryset = Pipeline.objects.for_user(self.request.user)

        # Apply type filter if specified
        pipeline_type = self.request.query_params.get(PipelineConstants.TYPE)
        if pipeline_type is not None:
            queryset = queryset.filter(pipeline_type=pipeline_type)

        # Filter by workflow ID if provided
        workflow_filter = self.request.query_params.get("workflow", None)
        if workflow_filter:
            queryset = queryset.filter(workflow_id=workflow_filter)

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
    def execute(self, request: Request) -> Response:
        serializer: ExecuteSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        execution_id = serializer.validated_data.get("execution_id", None)
        pipeline_id = serializer.validated_data[PK.PIPELINE_ID]

        execution = PipelineManager.execute_pipeline(
            request=request,
            pipeline_id=pipeline_id,
            execution_id=execution_id,
        )
        pipeline: Pipeline = PipelineProcessor.fetch_pipeline(pipeline_id)
        serializer = PipelineSerializer(pipeline)
        response_data = {
            PipelineExecutionKey.PIPELINE: serializer.data,
            PipelineExecutionKey.EXECUTION: execution.data,
        }
        return Response(data=response_data, status=status.HTTP_200_OK)

    def create(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pipeline_instance = serializer.save()
            # Create API key using the created instance
            KeyHelper.create_api_key(pipeline_instance, request)
        except IntegrityError:
            raise DuplicateData(
                f"{PipelineErrors.PIPELINE_EXISTS}, {PipelineErrors.DUPLICATE_API}"
            )
        return Response(data=serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Pipeline) -> None:
        pipeline_to_remove = str(instance.pk)
        super().perform_destroy(instance)
        return SchedulerHelper.remove_job(pipeline_to_remove)

    @action(detail=True, methods=["get"], url_path="users", permission_classes=[IsOwner])
    def list_of_shared_users(self, request: Request, pk: str | None = None) -> Response:
        """Returns the list of users the pipeline is shared with."""
        pipeline = self.get_object()
        serializer = SharedUserListSerializer(pipeline)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Override to handle sharing notifications."""
        instance = self.get_object()
        current_shared_users = set(instance.shared_users.all())

        response = super().partial_update(request, *args, **kwargs)

        if response.status_code == 200 and "shared_users" in request.data:
            try:
                instance.refresh_from_db()
                new_shared_users = set(instance.shared_users.all())
                newly_shared_users = new_shared_users - current_shared_users

                if newly_shared_users:
                    # Send notifications (if notification plugin is available)
                    try:
                        from plugins.notification.sharing_notification import (
                            SharingNotificationService,
                        )

                        notification_service = SharingNotificationService()
                        notification_service.send_sharing_notification(
                            resource_type="Pipeline",
                            resource_name=instance.pipeline_name,
                            resource_id=str(instance.id),
                            shared_by=request.user,
                            shared_to=list(newly_shared_users),
                            resource_instance=instance,
                        )
                    except ImportError:
                        logger.info("Notification plugin not available")
            except Exception as e:
                logger.error(f"Failed to send sharing notification: {e}")

        return response

    @action(detail=True, methods=["get"])
    def download_postman_collection(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Downloads a Postman Collection of the API deployment instance."""
        instance: Pipeline = self.get_object()
        api_key_inst = instance.apikey_set.filter(is_active=True).first()
        if not api_key_inst:
            logger.error(f"No active API key set for pipeline {instance}")
            raise NoActiveAPIKeyError(deployment_name=instance.pipeline_name)

        # Create a PostmanCollection for a Pipeline
        postman_collection = PostmanCollection.create(
            instance=instance, api_key=api_key_inst.api_key
        )
        response = HttpResponse(
            json.dumps(postman_collection.to_dict()), content_type="application/json"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{instance.pipeline_name}.json"'
        )
        return response
