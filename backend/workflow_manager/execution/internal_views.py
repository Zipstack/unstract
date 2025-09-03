"""Internal API Views for Workflow Execution Operations

This module contains internal API endpoints used by workers for execution finalization.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from workflow_manager.workflow_v2.models import WorkflowExecution

logger = logging.getLogger(__name__)


# =============================================================================
# EXECUTION FINALIZATION INTERNAL API VIEWS
# =============================================================================


@api_view(["POST"])
def finalize_workflow_execution_internal(request, execution_id):
    """Finalize workflow execution for internal API calls.

    This replaces the final execution logic that was previously done
    in the heavy Django workers, handling result aggregation and cleanup.
    """
    try:
        organization_id = getattr(request, "organization_id", None)

        # Get workflow execution
        try:
            execution = WorkflowExecution.objects.get(pk=execution_id)
            if organization_id and execution.organization_id != organization_id:
                return Response(
                    {"error": "Execution not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except WorkflowExecution.DoesNotExist:
            return Response(
                {"error": "Workflow execution not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Extract finalization parameters from request
        data = request.data
        final_status = data.get("final_status", "COMPLETED")
        total_files_processed = data.get(
            "total_files_processed"
        )  # No default - only update if provided
        total_execution_time = data.get("total_execution_time", 0.0)

        # Update execution with final status and metrics
        execution.status = final_status

        # Only update total_files if explicitly provided and positive
        if total_files_processed is not None and total_files_processed > 0:
            execution.total_files = total_files_processed

        execution.execution_time = total_execution_time

        # Handle completion timestamp - updated_at will be set automatically on save()

        # Save the execution
        execution.save()

        # Here you could add additional finalization logic like:
        # - Aggregating results from all file executions
        # - Generating final reports
        # - Triggering downstream notifications
        # - Cleaning up temporary resources

        logger.info(
            f"Finalized workflow execution {execution_id} with status {final_status}"
        )

        return Response(
            {
                "status": "finalized",
                "execution_id": execution_id,
                "final_status": final_status,
                "total_files_processed": total_files_processed,
                "total_execution_time": total_execution_time,
                "finalized_at": execution.modified_at.isoformat()
                if execution.modified_at
                else None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to finalize workflow execution {execution_id}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def cleanup_execution_resources_internal(request):
    """Cleanup execution resources for internal API calls.

    This handles cleanup of temporary files, cache entries, and other
    resources associated with workflow executions.
    """
    try:
        organization_id = getattr(request, "organization_id", None)

        # Extract cleanup parameters from request
        data = request.data
        execution_ids = data.get("execution_ids", [])
        cleanup_types = data.get("cleanup_types", ["cache", "temp_files"])

        cleanup_results = []

        for execution_id in execution_ids:
            try:
                # Verify execution exists and belongs to organization
                execution = WorkflowExecution.objects.get(pk=execution_id)
                if organization_id and execution.organization_id != organization_id:
                    cleanup_results.append(
                        {
                            "execution_id": execution_id,
                            "status": "skipped",
                            "reason": "not_in_organization",
                        }
                    )
                    continue

                cleanup_result = {
                    "execution_id": execution_id,
                    "status": "cleaned",
                    "cleanup_types": cleanup_types,
                    "items_cleaned": {},
                }

                # Handle different cleanup types
                if "cache" in cleanup_types:
                    # Clear execution cache entries
                    from workflow_manager.execution.execution_cache_utils import (
                        ExecutionCacheUtils,
                    )

                    cache_cleared = ExecutionCacheUtils.clear_execution_cache(
                        execution_id
                    )
                    cleanup_result["items_cleaned"]["cache_entries"] = cache_cleared

                if "temp_files" in cleanup_types:
                    # Clear temporary files (would need actual implementation)
                    cleanup_result["items_cleaned"]["temp_files"] = 0

                if "logs" in cleanup_types:
                    # Clear execution logs (would need actual implementation)
                    cleanup_result["items_cleaned"]["log_entries"] = 0

                cleanup_results.append(cleanup_result)

            except WorkflowExecution.DoesNotExist:
                cleanup_results.append(
                    {
                        "execution_id": execution_id,
                        "status": "not_found",
                        "reason": "execution_not_found",
                    }
                )
            except Exception as e:
                cleanup_results.append(
                    {"execution_id": execution_id, "status": "error", "reason": str(e)}
                )

        logger.info(f"Cleaned up resources for {len(execution_ids)} executions")

        return Response(
            {
                "status": "completed",
                "total_executions": len(execution_ids),
                "cleanup_results": cleanup_results,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Failed to cleanup execution resources: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def execution_finalization_status_internal(request, execution_id):
    """Get execution finalization status for internal API calls."""
    try:
        organization_id = getattr(request, "organization_id", None)

        # Get workflow execution
        try:
            execution = WorkflowExecution.objects.get(pk=execution_id)
            if organization_id and execution.organization_id != organization_id:
                return Response(
                    {"error": "Execution not found in organization"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except WorkflowExecution.DoesNotExist:
            return Response(
                {"error": "Workflow execution not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Determine finalization status
        is_finalized = execution.status in ["COMPLETED", "FAILED", "CANCELLED"]

        return Response(
            {
                "execution_id": execution_id,
                "is_finalized": is_finalized,
                "current_status": execution.status,
                "total_files": execution.total_files,
                "execution_time": execution.execution_time,
                "created_at": execution.created_at.isoformat(),
                "completed_at": execution.completed_at.isoformat()
                if execution.completed_at
                else None,
                "last_updated": execution.modified_at.isoformat()
                if execution.modified_at
                else None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(
            f"Failed to get execution finalization status for {execution_id}: {e}"
        )
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
