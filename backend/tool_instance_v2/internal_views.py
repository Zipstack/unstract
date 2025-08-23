"""Internal API Views for Tool Instance Operations

This module contains internal API endpoints used by workers for tool execution.
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from utils.organization_utils import filter_queryset_by_organization

from tool_instance_v2.models import ToolInstance
from tool_instance_v2.serializers import ToolInstanceSerializer
from tool_instance_v2.tool_processor import ToolProcessor

logger = logging.getLogger(__name__)


class ToolExecutionInternalViewSet(viewsets.ModelViewSet):
    """Internal API for tool execution operations used by lightweight workers."""

    serializer_class = ToolInstanceSerializer

    def get_queryset(self):
        # Filter by organization context set by internal API middleware
        # Use relationship path: ToolInstance -> Workflow -> Organization
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
