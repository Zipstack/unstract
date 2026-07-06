import json
import logging
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from api_v2.exceptions import NoActiveAPIKeyError
from api_v2.key_helper import KeyHelper
from api_v2.postman_collection.dto import PostmanCollection
from django.db import IntegrityError
from django.db.models import F, QuerySet
from django.http import HttpResponse
from permissions.membership_views import OwnerManagementMixin
from permissions.permission import IsOwner, IsOwnerOrSharedUserOrSharedToOrg
from permissions.resource_share_views import ResourceShareManagementMixin
from permissions.roles import ResourceRole
from plugins import get_plugin
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from scheduler.helper import SchedulerHelper
from utils.pagination import CustomPagination

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

notification_plugin = get_plugin("notification")
if notification_plugin:
    from plugins.notification.constants import ResourceType

logger = logging.getLogger(__name__)


class PipelineViewSet(
    OwnerManagementMixin, ResourceShareManagementMixin, viewsets.ModelViewSet
):
    versioning_class = URLPathVersioning
    queryset = Pipeline.objects.all()
    pagination_class = CustomPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "last_run_time", "pipeline_name", "run_count"]
    # Note: Default ordering with nulls_last is applied in get_queryset()
    # DRF's ordering attribute doesn't support nulls_last natively
    notification_resource_name_field = "pipeline_name"

    def get_notification_resource_type(self, resource: Any) -> str | None:
        # Only ETL/TASK pipelines map to a notification ResourceType.
        if not notification_plugin:
            return None
        if resource.pipeline_type in (ResourceType.ETL.value, ResourceType.TASK.value):
            return resource.pipeline_type
        return None

    def get_permissions(self) -> list[Any]:
        if self.action in [
            "destroy",
            "partial_update",
            "update",
            "add_co_owner",
            "remove_co_owner",
        ]:
            return [IsOwner()]
        return [IsOwnerOrSharedUserOrSharedToOrg()]

    serializer_class = PipelineSerializer

    def get_queryset(self) -> QuerySet:
        # Use for_user manager method to include shared pipelines
        # Avoid per-row queries for owner/co-owner + creator fields in list views
        queryset = (
            Pipeline.objects.for_user(self.request.user)
            .select_related("created_by")
            .prefetch_related("memberships")
        )

        # Apply type filter if specified
        pipeline_type = self.request.query_params.get(PipelineConstants.TYPE)
        if pipeline_type is not None:
            queryset = queryset.filter(pipeline_type=pipeline_type)

        # Filter by workflow ID if provided
        workflow_filter = self.request.query_params.get("workflow", None)
        if workflow_filter:
            queryset = queryset.filter(workflow_id=workflow_filter)

        # Search by pipeline name
        search = self.request.query_params.get("search", None)
        if search:
            queryset = queryset.filter(pipeline_name__icontains=search)

        # Exact-match lookup (distinct from the icontains search above).
        pipeline_name = self.request.query_params.get(PK.PIPELINE_NAME)
        if pipeline_name:
            queryset = queryset.filter(pipeline_name=pipeline_name)

        # Apply default ordering: last_run_time desc (nulls last), then created_at desc
        # This ensures pipelines with recent runs appear first, never-run pipelines at end
        queryset = queryset.order_by(
            F("last_run_time").desc(nulls_last=True),
            F("created_at").desc(),
        )

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
        # ``created_by`` is audit-only; the creator's access flows through an
        # OWNER membership row (UN-2202 co-owners).
        pipeline_instance.memberships.get_or_create(
            user_id=request.user.id, defaults={"role": ResourceRole.OWNER}
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

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Override to handle sharing notifications."""
        instance = self.get_object()
        before = self.snapshot_share_axes(instance)

        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200 and notification_plugin:
            self._notify_shared_users(instance, before, request.data, request.user)
        return response

    def _notify_shared_users(
        self,
        instance: Pipeline,
        before: dict[str, set[Any]],
        request_data: dict[str, Any],
        actor: Any,
    ) -> None:
        """Email users newly added to ``shared_users`` (best-effort).

        Only ETL/TASK pipelines map to a notification ``ResourceType``;
        DEFAULT/APP pipelines have no analogue and skip the fan-out.
        """
        users_diff = self.diff_share_axes(instance, before, request_data).get(
            "shared_users"
        )
        if not (users_diff and users_diff.added):
            return
        if instance.pipeline_type not in (
            ResourceType.ETL.value,
            ResourceType.TASK.value,
        ):
            return
        try:
            service_class = notification_plugin["service_class"]
            notification_service = service_class()
            notification_service.send_sharing_notification(
                resource_type=instance.pipeline_type,
                resource_name=instance.pipeline_name,
                resource_id=str(instance.id),
                shared_by=actor,
                shared_to=list(users_diff.added),
                resource_instance=instance,
            )
            logger.info(
                "Sent sharing notifications for %s to %d users",
                instance.pipeline_type,
                len(users_diff.added),
            )
        except Exception as e:
            logger.exception(
                "Failed to send sharing notification, continuing update though: %s",
                str(e),
            )

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
