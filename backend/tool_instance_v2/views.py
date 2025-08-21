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
from utils.filtering import FilterHelper
from utils.user_session import UserSessionUtils
from workflow_manager.workflow_v2.constants import WorkflowKey

from backend.constants import RequestKey
from tool_instance_v2.constants import ToolInstanceErrors, ToolKey
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.exceptions import FetchToolListFailed, ToolFunctionIsMandatory
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.serializers import (
    ToolInstanceReorderSerializer as TIReorderSerializer,
)
from tool_instance_v2.serializers import ToolInstanceSerializer
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from tool_instance_v2.tool_processor import ToolProcessor

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


# Only GET is allowed, and this is safe.
@api_view(["GET"])
def prompt_studio_tool_count(request: Request) -> Response:  # NOSONAR
    """Get count of prompt studio tools.

    Returns count of valid prompt studio tools available in the Tool registry.
    Only counts tools that have UUID as function names.
    """
    if request.method == "GET":
        try:
            logger.info("Fetching prompt studio tool count from the tool.")
            tool_count = ToolProcessor.get_prompt_studio_tool_count(request.user)
            return Response(
                data={"count": tool_count},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error(f"Failed to fetch prompt studio tools: {exc}")
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
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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


# =============================================================================
# INTERNAL API VIEWS - Used by Celery workers for service-to-service communication
# =============================================================================


class ToolExecutionInternalViewSet(viewsets.ModelViewSet):
    """Internal API for tool execution operations used by lightweight workers."""

    serializer_class = ToolInstanceSerializer

    def get_queryset(self):
        # Filter by organization context set by internal API middleware
        # Use relationship path: ToolInstance -> Workflow -> Organization
        from utils.organization_utils import filter_queryset_by_organization

        queryset = ToolInstance.objects.all()
        return filter_queryset_by_organization(
            queryset, self.request, "workflow__organization"
        )

    def execute_tool(self, request, pk=None):
        """Execute a specific tool with provided input data.

        This replaces the direct tool execution that was previously done
        in the heavy Django workers.
        """
        try:
            tool_instance = self.get_object()

            # Extract execution parameters from request
            input_data = request.data.get("input_data", {})
            file_data = request.data.get("file_data", {})
            execution_context = request.data.get("execution_context", {})

            # Execute tool using existing tool processor
            execution_result = ToolProcessor.execute_tool(
                tool_instance=tool_instance,
                input_data=input_data,
                file_data=file_data,
                context=execution_context,
                user=request.user,
            )

            return Response(
                {
                    "status": "success",
                    "tool_instance_id": str(tool_instance.id),
                    "execution_result": execution_result,
                    "tool_function": tool_instance.tool_function,
                    "step": tool_instance.step,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Tool execution failed for tool {pk}: {e}")
            return Response(
                {
                    "status": "error",
                    "error_message": str(e),
                    "tool_instance_id": str(pk) if pk else None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
def tool_execution_status_internal(request, execution_id):
    """Get tool execution status for internal API calls."""
    try:
        # This would track tool execution status
        # For now, return a basic status structure
        return Response(
            {
                "execution_id": execution_id,
                "status": "completed",  # Could be: pending, running, completed, failed
                "progress": 100,
                "results": [],
                "error_message": None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to get tool execution status for {execution_id}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def tool_by_id_internal(request, tool_id):
    """Get tool information by tool ID for internal API calls."""
    try:
        from .tool_processor import ToolProcessor

        logger.info(f"Getting tool information for tool ID: {tool_id}")

        # Get tool from registry using ToolProcessor
        try:
            tool = ToolProcessor.get_tool_by_uid(tool_id)
            logger.info(f"Successfully retrieved tool from ToolProcessor: {tool_id}")
        except Exception as tool_fetch_error:
            logger.error(
                f"Failed to fetch tool {tool_id} from ToolProcessor: {tool_fetch_error}"
            )
            # Return fallback using Structure Tool image (which actually exists)
            from django.conf import settings

            return Response(
                {
                    "tool": {
                        "tool_id": tool_id,
                        "properties": {
                            "displayName": f"Missing Tool ({tool_id[:8]}...)",
                            "functionName": tool_id,
                            "description": "Tool not found in registry or Prompt Studio",
                            "toolVersion": "unknown",
                        },
                        "image_name": settings.STRUCTURE_TOOL_IMAGE_NAME,
                        "image_tag": settings.STRUCTURE_TOOL_IMAGE_TAG,
                        "name": f"Missing Tool ({tool_id[:8]}...)",
                        "description": "Tool not found in registry or Prompt Studio",
                        "version": "unknown",
                        "note": "Fallback data for missing tool",
                    }
                },
                status=status.HTTP_200_OK,
            )

        # Convert Properties object to dict for JSON serialization
        properties_dict = {}
        try:
            if hasattr(tool.properties, "to_dict"):
                # Use the to_dict method if available (which handles Adapter serialization)
                properties_dict = tool.properties.to_dict()
                logger.info(f"Properties serialized using to_dict() for tool {tool_id}")
            elif hasattr(tool.properties, "dict"):
                properties_dict = tool.properties.dict()
                logger.info(f"Properties serialized using dict() for tool {tool_id}")
            elif hasattr(tool.properties, "__dict__"):
                properties_dict = tool.properties.__dict__
                logger.info(f"Properties serialized using __dict__ for tool {tool_id}")
            else:
                # Try to convert to dict if it's iterable
                try:
                    properties_dict = dict(tool.properties)
                    logger.info(
                        f"Properties serialized using dict conversion for tool {tool_id}"
                    )
                except (TypeError, ValueError):
                    properties_dict = {"default": "true"}  # Fallback
                    logger.warning(f"Using fallback properties for tool {tool_id}")
        except Exception as props_error:
            logger.error(
                f"Failed to serialize properties for tool {tool_id}: {props_error}"
            )
            properties_dict = {"error": "serialization_failed"}

        # Handle spec serialization if needed
        if hasattr(tool, "spec") and tool.spec:
            if hasattr(tool.spec, "to_dict"):
                tool.spec.to_dict()
            elif hasattr(tool.spec, "__dict__"):
                pass

        # Return tool information with essential fields only to avoid serialization issues
        return Response(
            {
                "tool": {
                    "tool_id": tool_id,
                    "properties": properties_dict,
                    "image_name": str(tool.image_name)
                    if tool.image_name
                    else "default-tool",
                    "image_tag": str(tool.image_tag) if tool.image_tag else "latest",
                    "name": getattr(tool, "name", tool_id),
                    "description": getattr(tool, "description", ""),
                    "version": getattr(tool, "version", "latest"),
                }
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to get tool information for {tool_id}: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")

        # Always return fallback data instead of error to allow workflow to continue
        from django.conf import settings

        return Response(
            {
                "tool": {
                    "tool_id": tool_id,
                    "properties": {
                        "displayName": f"Error Tool ({tool_id[:8]}...)",
                        "functionName": tool_id,
                        "description": f"Error processing tool: {str(e)[:100]}",
                        "toolVersion": "error",
                    },
                    "image_name": settings.STRUCTURE_TOOL_IMAGE_NAME,
                    "image_tag": settings.STRUCTURE_TOOL_IMAGE_TAG,
                    "name": f"Error Tool ({tool_id[:8]}...)",
                    "description": f"Error: {str(e)[:100]}",
                    "version": "error",
                    "error": str(e),
                    "note": "Fallback data for tool processing error",
                }
            },
            status=status.HTTP_200_OK,  # Return 200 to allow workflow to continue
        )


@api_view(["GET"])
def tool_instances_by_workflow_internal(request, workflow_id):
    """Get tool instances for a workflow for internal API calls."""
    try:
        from utils.organization_utils import filter_queryset_by_organization
        from workflow_manager.workflow_v2.models.workflow import Workflow

        logger.info(f"Getting tool instances for workflow: {workflow_id}")

        # Get workflow with organization filtering first (via DefaultOrganizationManagerMixin)
        try:
            workflow = Workflow.objects.get(id=workflow_id)
            logger.info(f"Found workflow: {workflow.id}")
        except Workflow.DoesNotExist:
            logger.error(f"Workflow not found: {workflow_id}")
            return Response(
                {"error": "Workflow not found or access denied"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get tool instances for the workflow with organization filtering
        # Filter through the relationship: ToolInstance -> Workflow -> Organization
        tool_instances_queryset = ToolInstance.objects.filter(workflow=workflow)
        tool_instances_queryset = filter_queryset_by_organization(
            tool_instances_queryset, request, "workflow__organization"
        )
        tool_instances = tool_instances_queryset.order_by("step")
        logger.info(f"Found {len(tool_instances)} tool instances")

        # Serialize the tool instances
        try:
            logger.info("Starting serialization of tool instances")
            serializer = ToolInstanceSerializer(tool_instances, many=True)
            logger.info("Accessing serializer.data")
            serializer_data = serializer.data
            logger.info(f"Serialization completed, got {len(serializer_data)} items")
        except Exception as serializer_error:
            logger.error(f"Serialization error: {serializer_error}")
            # Try to return basic data without enhanced tool information
            basic_data = []
            for instance in tool_instances:
                basic_data.append(
                    {
                        "id": str(instance.id),
                        "tool_id": instance.tool_id,
                        "step": instance.step,
                        "metadata": instance.metadata,
                    }
                )
            logger.info(f"Returning {len(basic_data)} basic tool instances")
            return Response(
                {
                    "workflow_id": workflow_id,
                    "tool_instances": basic_data,
                    "total_count": len(tool_instances),
                    "note": "Basic data returned due to serialization error",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "workflow_id": workflow_id,
                "tool_instances": serializer_data,
                "total_count": len(tool_instances),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to get tool instances for workflow {workflow_id}: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
