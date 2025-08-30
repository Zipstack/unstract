"""Internal API Views for Worker Communication

This module provides internal API endpoints that workers use to communicate
with Django backend for database operations only. All business logic has been
moved to workers.

NOTE: Many sophisticated endpoints are now implemented in internal_views.py
using class-based views. This file contains simpler function-based views
for basic operations.
"""

import logging

from account_v2.models import Organization
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from tool_instance_v2.models import ToolInstance

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

logger = logging.getLogger(__name__)


@api_view(["GET"])
def get_workflow_execution_data(request, execution_id: str):
    """Get workflow execution data for workers.

    Args:
        execution_id: Workflow execution ID

    Returns:
        JSON response with workflow and execution data
    """
    try:
        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get execution with organization filtering
        execution = WorkflowExecution.objects.select_related("workflow").get(
            id=execution_id, workflow__organization_id=org_id
        )

        workflow = execution.workflow

        # Prepare workflow data
        workflow_data = {
            "id": str(workflow.id),
            "workflow_name": workflow.workflow_name,
            "execution_details": workflow.execution_details,
            "organization_id": workflow.organization_id,
        }

        # Prepare execution data
        execution_data = {
            "id": str(execution.id),
            "status": execution.status,
            "execution_mode": execution.execution_mode,
            "execution_method": execution.execution_method,
            "execution_type": execution.execution_type,
            "pipeline_id": execution.pipeline_id,
            "total_files": execution.total_files,
            "completed_files": execution.completed_files,
            "failed_files": execution.failed_files,
            "execution_log_id": execution.execution_log_id,  # Include for WebSocket messaging
        }

        return Response(
            {
                "workflow": workflow_data,
                "execution": execution_data,
            }
        )

    except WorkflowExecution.DoesNotExist:
        return Response(
            {"error": f"Workflow execution {execution_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Error getting workflow execution data: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_tool_instances_by_workflow(request, workflow_id: str):
    """Get tool instances for a workflow.

    Args:
        workflow_id: Workflow ID

    Returns:
        JSON response with tool instances data
    """
    try:
        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            logger.error(f"Missing X-Organization-ID header for workflow {workflow_id}")
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"Getting tool instances for workflow {workflow_id}, org {org_id}")

        # Get tool instances with organization filtering
        # First check if workflow exists and belongs to organization
        try:
            # Get organization object first (org_id is the organization_id string field)
            logger.info(f"Looking up organization with organization_id: {org_id}")
            organization = Organization.objects.get(organization_id=org_id)
            logger.info(
                f"Found organization: {organization.id} - {organization.display_name}"
            )

            logger.info(
                f"Looking up workflow {workflow_id} for organization {organization.id}"
            )
            workflow = Workflow.objects.get(id=workflow_id, organization=organization)
            logger.info(f"Found workflow: {workflow.workflow_name}")

        except Organization.DoesNotExist:
            logger.error(f"Organization not found: {org_id}")
            return Response(
                {"error": f"Organization {org_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Workflow.DoesNotExist:
            logger.error(f"Workflow {workflow_id} not found for organization {org_id}")
            return Response(
                {"error": f"Workflow {workflow_id} not found for organization {org_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error during organization/workflow lookup: {e}",
                exc_info=True,
            )
            return Response(
                {"error": "Database lookup error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Get tool instances for the workflow
        tool_instances = ToolInstance.objects.filter(workflow=workflow).order_by("step")

        # Prepare tool instances data
        instances_data = []
        for instance in tool_instances:
            instance_data = {
                "id": str(instance.id),
                "tool_id": instance.tool_id,
                "step": instance.step,
                "status": instance.status,
                "version": instance.version,
                "metadata": instance.metadata,
                "input": instance.input,
                "output": instance.output,
            }
            instances_data.append(instance_data)

        return Response(
            {
                "tool_instances": instances_data,
            }
        )

    except Exception as e:
        logger.error(
            f"Error getting tool instances for workflow {workflow_id}: {e}", exc_info=True
        )
        return Response(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def create_file_execution_batch(request):
    """Create a batch of file executions for workers.

    Returns:
        JSON response with batch creation result
    """
    try:
        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            logger.error(
                "Missing X-Organization-ID header for file execution batch creation"
            )
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For now, return a simple response indicating batch creation
        # This would be expanded based on actual requirements
        return Response(
            {
                "batch_id": "temp-batch-id",
                "status": "created",
                "organization_id": org_id,
            }
        )

    except Exception as e:
        logger.error(f"Error creating file execution batch: {e}", exc_info=True)
        return Response(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def update_file_execution_batch_status(request):
    """Update file execution batch status for workers.

    Returns:
        JSON response with batch status update result
    """
    try:
        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            logger.error(
                "Missing X-Organization-ID header for file execution batch status update"
            )
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For now, return a simple response indicating status update
        # This would be expanded based on actual requirements
        return Response(
            {
                "status": "updated",
                "organization_id": org_id,
            }
        )

    except Exception as e:
        logger.error(f"Error updating file execution batch status: {e}", exc_info=True)
        return Response(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def create_workflow_execution(request):
    """Create a new workflow execution.

    Returns:
        JSON response with execution ID
    """
    try:
        data = request.data

        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get workflow with organization filtering
        # First get organization object, then lookup workflow
        try:
            organization = Organization.objects.get(organization_id=org_id)
            workflow = Workflow.objects.get(
                id=data["workflow_id"], organization=organization
            )
        except Organization.DoesNotExist:
            return Response(
                {"error": f"Organization {org_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create execution with log_events_id for WebSocket messaging
        log_events_id = data.get("log_events_id")
        # If log_events_id not provided, fall back to pipeline_id for backward compatibility
        execution_log_id = log_events_id if log_events_id else data.get("pipeline_id")

        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            pipeline_id=data.get("pipeline_id"),
            execution_mode=data.get("mode", WorkflowExecution.Mode.INSTANT),
            execution_method=WorkflowExecution.Method.SCHEDULED
            if data.get("scheduled")
            else WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.STEP
            if data.get("single_step")
            else WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.PENDING.value,
            total_files=data.get("total_files", 0),
            execution_log_id=execution_log_id,  # Set execution_log_id for WebSocket messaging
        )

        # Set tags if provided
        if data.get("tags"):
            # Handle tags logic if needed
            pass

        return Response(
            {
                "execution_id": str(execution.id),
                "status": execution.status,
                "execution_log_id": execution.execution_log_id,  # Return for workers to use
            }
        )

    except Workflow.DoesNotExist:
        return Response({"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error creating workflow execution: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PUT"])
def update_workflow_execution_status(request):
    """Update workflow execution status.

    Returns:
        JSON response with success status
    """
    try:
        data = request.data
        execution_id = data.get("execution_id")

        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get and update execution
        execution = WorkflowExecution.objects.get(
            id=execution_id, workflow__organization_id=org_id
        )

        # Update fields
        fields_updated = []
        if "status" in data:
            old_status = execution.status
            execution.status = data["status"]
            fields_updated.append(f"status: {old_status} -> {data['status']}")
        if "error_message" in data:
            execution.error_message = data["error_message"][:500]  # Limit length
            fields_updated.append("error_message")
        if "total_files" in data:
            execution.total_files = data["total_files"]
            fields_updated.append(f"total_files: {data['total_files']}")
        if "completed_files" in data:
            execution.completed_files = data["completed_files"]
            fields_updated.append(f"completed_files: {data['completed_files']}")
        if "failed_files" in data:
            execution.failed_files = data["failed_files"]
            fields_updated.append(f"failed_files: {data['failed_files']}")
        if data.get("increment_attempt"):
            execution.attempts += 1
            fields_updated.append("attempts")

        logger.info(f"Updating execution {execution_id}: {', '.join(fields_updated)}")
        execution.save()
        logger.info(
            f"Successfully saved execution {execution_id} with status: {execution.status}"
        )

        # Emit WebSocket event for real-time UI updates
        try:
            from utils.log_events import _emit_websocket_event

            # Create status update event data
            status_data = {
                "execution_id": str(execution.id),
                "status": execution.status,
                "total_files": execution.total_files,
                "completed_files": execution.completed_files,
                "failed_files": execution.failed_files,
                "workflow_id": str(execution.workflow.id),
                "pipeline_id": execution.pipeline_id,
            }

            # Emit to execution-specific room and general workflow room
            _emit_websocket_event(
                room=f"execution:{execution.id}",
                event="execution_status_update",
                data=status_data,
            )

            # Also emit to workflow room for general workflow listeners
            _emit_websocket_event(
                room=f"workflow:{execution.workflow.id}",
                event="execution_status_update",
                data=status_data,
            )

            logger.debug(
                f"WebSocket events emitted for execution status update: {execution.id} -> {execution.status}"
            )

        except Exception as e:
            # Don't fail the request if WebSocket emission fails
            logger.warning(
                f"Failed to emit WebSocket event for execution status update: {e}"
            )

        return Response(
            {
                "success": True,
                "execution_id": str(execution.id),
                "status": execution.status,
            }
        )

    except WorkflowExecution.DoesNotExist:
        return Response(
            {"error": "Workflow execution not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error updating workflow execution status: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def compile_workflow(request):
    """Compile workflow for workers.

    This is a database-only operation that workers need.

    Returns:
        JSON response with compilation result
    """
    try:
        data = request.data
        workflow_id = data.get("workflow_id")

        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For now, return success since compilation logic needs to be migrated
        # TODO: Implement actual compilation logic in workers

        return Response(
            {
                "success": True,
                "workflow_id": workflow_id,
            }
        )

    except Exception as e:
        logger.error(f"Error compiling workflow: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def submit_file_batch_for_processing(request):
    """Submit file batch for processing by workers.

    This endpoint receives batch data and returns immediately,
    as actual processing is handled by Celery workers.

    Returns:
        JSON response with batch submission status
    """
    try:
        batch_data = request.data

        # Get organization from header
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return Response(
                {"error": "X-Organization-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Add organization ID to file_data where WorkerFileData expects it
        if "file_data" in batch_data:
            batch_data["file_data"]["organization_id"] = org_id
        else:
            # Fallback: add at top level for backward compatibility
            batch_data["organization_id"] = org_id

        # Submit to file processing worker queue using Celery
        try:
            from backend.celery_service import app as celery_app

            # Submit the batch data to the file processing worker using send_task
            # This calls the task by name without needing to import it
            task_result = celery_app.send_task(
                "process_file_batch",  # Task name as defined in workers/file_processing/tasks.py
                args=[batch_data],  # Pass batch_data as first argument
                queue="file_processing",  # Send to file processing queue
            )

            logger.info(
                f"Successfully submitted file batch {batch_data.get('batch_id')} to worker queue (task: {task_result.id})"
            )

            return Response(
                {
                    "success": True,
                    "batch_id": batch_data.get("batch_id"),
                    "celery_task_id": task_result.id,
                    "message": "Batch submitted for processing",
                }
            )

        except Exception as e:
            logger.error(f"Failed to submit batch to worker queue: {e}")
            return Response(
                {"error": f"Failed to submit batch for processing: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Exception as e:
        logger.error(f"Error submitting file batch: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# NOTE: The following endpoints are now implemented as sophisticated class-based views in internal_views.py:
# - get_workflow_definition -> WorkflowDefinitionAPIView
# - get_pipeline_type -> PipelineTypeAPIView
# - get_workflow_endpoints -> WorkflowEndpointAPIView
# - batch_update_execution_status -> BatchStatusUpdateAPIView
# - create_file_batch -> FileBatchCreateAPIView
# - increment_files -> FileCountIncrementAPIView
# - create_file_history_entry -> FileHistoryCreateView
# - check_file_history_batch -> FileHistoryBatchCheckView
