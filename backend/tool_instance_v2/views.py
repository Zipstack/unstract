import logging
import uuid
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from django.db import IntegrityError
from django.db.models.query import QuerySet
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance_v2.constants import ToolInstanceErrors
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.constants import ToolKey
from tool_instance_v2.exceptions import FetchToolListFailed, ToolFunctionIsMandatory
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.serializers import (
    ToolInstanceReorderSerializer as TIReorderSerializer,
)
from tool_instance_v2.serializers import ToolInstanceSerializer
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from tool_instance_v2.tool_processor import ToolProcessor
from utils.filtering import FilterHelper
from utils.user_session import UserSessionUtils
from workflow_manager.workflow_v2.constants import WorkflowKey

from backend.constants import RequestKey

logger = logging.getLogger(__name__)


@api_view(["GET"])
def tool_settings_schema(request: Request) -> Response:
    if request.method == "GET":
        tool_function = request.GET.get(ToolKey.FUNCTION_NAME)
        if tool_function is None or tool_function == "":
            raise ToolFunctionIsMandatory()

        json_schema = ToolProcessor.get_json_schema_for_tool(
            tool_uid=tool_function, user=request.user
        )
        return Response(data=json_schema, status=status.HTTP_200_OK)


@api_view(("GET",))
def get_tool_list(request: Request) -> Response:
    """Get tool list.

    Fetches a list of tools available in the Tool registry
    """
    if request.method == "GET":
        try:
            logger.info("Fetching tools from the tool registry...")
            return Response(
                data=ToolProcessor.get_tool_list(request.user),
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error(f"Failed to fetch tools: {exc}")
            raise FetchToolListFailed


class ToolInstanceViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = ToolInstanceSerializer

    def get_queryset(self) -> QuerySet:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.PROJECT,
            RequestKey.CREATED_BY,
            RequestKey.WORKFLOW,
        )
        if filter_args:
            queryset = ToolInstance.objects.filter(
                created_by=self.request.user, **filter_args
            )
        else:
            queryset = ToolInstance.objects.filter(created_by=self.request.user)
        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action == "reorder":
            return TIReorderSerializer
        else:
            return ToolInstanceSerializer

    def create(self, request: Any) -> Response:
        """Create tool instance.

        Creates a tool instance, useful to add them directly to a
        workflow. Its an alternative to creating tool instances through
        the LLM response.
        """

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolInstanceErrors.TOOL_EXISTS}, "
                f"{ToolInstanceErrors.DUPLICATE_API}"
            )
        instance: ToolInstance = serializer.instance
        ToolInstanceHelper.update_metadata_with_default_values(
            instance, user=request.user
        )
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_destroy(self, instance: ToolInstance) -> None:
        """Deletes a tool instance and decrements successor instance's steps.

        Args:
            instance (ToolInstance): Instance being deleted.
        """
        lookup = {"step__gt": instance.step}
        next_tool_instances: list[ToolInstance] = (
            ToolInstanceHelper.get_tool_instances_by_workflow(
                instance.workflow.id, TIKey.STEP, lookup=lookup
            )
        )
        super().perform_destroy(instance)

        for instance in next_tool_instances:
            instance.step = instance.step - 1
            instance.save()

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Allows partial updates on a tool instance."""
        instance: ToolInstance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get(TIKey.METADATA):
            metadata: dict[str, Any] = serializer.validated_data.get(TIKey.METADATA)

            # TODO: Move update logic into serializer
            organization_id = UserSessionUtils.get_organization_id(request)
            ToolInstanceHelper.update_instance_metadata(
                organization_id,
                instance,
                metadata,
            )
            return Response(serializer.data)
        return super().partial_update(request, *args, **kwargs)

    def reorder(self, request: Any, **kwargs: Any) -> Response:
        """Reorder tool instances.

        Reorders the tool instances based on a list of UUIDs.
        """
        serializer: TIReorderSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wf_id = serializer.validated_data[WorkflowKey.WF_ID]
        instances_to_reorder: list[uuid.UUID] = serializer.validated_data[
            WorkflowKey.WF_TOOL_INSTANCES
        ]

        ToolInstanceHelper.reorder_tool_instances(instances_to_reorder)
        tool_instances = ToolInstance.objects.get_instances_for_workflow(workflow=wf_id)
        ti_serializer = ToolInstanceSerializer(instance=tool_instances, many=True)
        return Response(ti_serializer.data, status=status.HTTP_200_OK)
