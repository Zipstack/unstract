"""Scheduler Worker Tasks

This worker handles scheduled pipeline executions, migrated from @backend/scheduler/tasks.py
to support the new workers architecture while maintaining backward compatibility.
"""

import traceback
from typing import Any

from celery import shared_task
from shared.enums.status_enums import PipelineStatus
from shared.enums.task_enums import QueueName
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import WorkerLogger
from shared.legacy.api_client_singleton import get_singleton_api_client
from shared.models.pipeline_models import PipelineApiResponse
from shared.models.scheduler_models import (
    ExecutionMode,
    ScheduledPipelineContext,
    SchedulerExecutionResult,
    WorkflowExecutionRequest,
)

# Import the exact backend logic to ensure consistency

logger = WorkerLogger.get_logger(__name__)

# Initialize worker configuration
config = WorkerConfig.from_env("SCHEDULER")


def _execute_scheduled_workflow(
    api_client,
    context: ScheduledPipelineContext,
) -> SchedulerExecutionResult:
    """Execute scheduled workflow using worker-native logic with type safety.

    This replaces the Django-heavy backend complete_execution method with
    a worker-native implementation that uses internal APIs and dataclasses.

    Args:
        api_client: Internal API client instance
        context: Scheduled pipeline execution context

    Returns:
        SchedulerExecutionResult with execution status and details
    """
    try:
        logger.info(
            f"Creating workflow execution for scheduled pipeline: {context.pipeline_name}"
        )

        # Step 1: Create workflow execution via internal API using dataclass
        # For scheduled executions, let backend handle execution_log_id (falls back to pipeline_id)
        # This matches the backend logic: log_events_id if provided, else pipeline_id
        execution_request = WorkflowExecutionRequest(
            workflow_id=context.workflow_id,
            pipeline_id=context.pipeline_id,
            organization_id=context.organization_id,
            single_step=False,
            mode=ExecutionMode.QUEUE,
            total_files=0,  # Will be updated during execution
            scheduled=True,
            # log_events_id=None - let backend fall back to pipeline_id for scheduled executions
        )

        workflow_execution = api_client.create_workflow_execution(
            execution_request.to_dict()
        )
        execution_id = workflow_execution.get("execution_id")

        if not execution_id:
            return SchedulerExecutionResult.error(
                error="Failed to create workflow execution",
                workflow_id=context.workflow_id,
                pipeline_id=context.pipeline_id,
            )

        logger.info(
            f"[exec:{execution_id}] [pipeline:{context.pipeline_id}] Created workflow execution for scheduled pipeline {context.pipeline_name}"
        )

        # Step 2: Trigger async workflow execution via direct Celery dispatch
        logger.info(
            f"[exec:{execution_id}] [pipeline:{context.pipeline_id}] Triggering async execution for workflow {context.workflow_id}"
        )

        # Use Celery to dispatch async execution task directly (like backend scheduler does)
        from celery import current_app

        logger.info(
            f"[exec:{execution_id}] [pipeline:{context.pipeline_id}] Dispatching async_execute_bin task for scheduled execution"
        )

        try:
            # Dispatch the Celery task directly to the general queue
            async_result = current_app.send_task(
                "async_execute_bin",
                args=[
                    context.organization_id,  # schema_name (organization_id)
                    context.workflow_id,  # workflow_id
                    execution_id,  # execution_id
                    {},  # hash_values_of_files (empty for scheduled)
                    True,  # scheduled (THIS IS A SCHEDULED EXECUTION)
                ],
                kwargs={
                    "use_file_history": context.use_file_history,  # Pass as kwarg
                    "pipeline_id": context.pipeline_id,  # CRITICAL FIX: Pass pipeline_id for direct status updates
                },
                queue=QueueName.CELERY,  # Route to celery queue (what general worker listens to)
            )

            task_id = async_result.id
            logger.info(
                f"[exec:{execution_id}] [pipeline:{context.pipeline_id}] Successfully dispatched async_execute_bin task {task_id} for scheduled execution"
            )

            execution_response = SchedulerExecutionResult.success(
                execution_id=execution_id,
                workflow_id=context.workflow_id,
                pipeline_id=context.pipeline_id,
                task_id=task_id,
                message="Async execution task dispatched successfully",
            )
        except Exception as e:
            logger.error(f"Failed to dispatch async execution task: {e}")
            execution_response = SchedulerExecutionResult.error(
                error=f"Failed to dispatch async execution: {str(e)}",
                execution_id=execution_id,
                workflow_id=context.workflow_id,
                pipeline_id=context.pipeline_id,
            )

        if execution_response.is_success:
            logger.info(
                f"Successfully started scheduled execution {execution_id} for pipeline '{context.pipeline_name}'"
            )
            return execution_response  # Already a SchedulerExecutionResult
        else:
            logger.error(
                f"Failed to start async execution for pipeline '{context.pipeline_name}': {execution_response.error}"
            )
            return execution_response  # Already a SchedulerExecutionResult with error

    except Exception as e:
        logger.error(f"Exception in scheduled workflow execution: {e}")
        return SchedulerExecutionResult.error(
            error=f"Scheduler execution failed: {str(e)}",
            workflow_id=context.workflow_id,
            pipeline_id=context.pipeline_id,
        )


@shared_task(name="scheduler.tasks.execute_pipeline_task", bind=True)
def execute_pipeline_task(
    self,
    workflow_id: Any,
    org_schema: Any,
    execution_action: Any,
    execution_id: Any,
    pipepline_id: Any,  # Note: keeping original typo for compatibility
    with_logs: Any,
    name: Any,
) -> None:
    """Execute pipeline task - maintains exact signature from backend scheduler.

    This is the main entry point for scheduled pipeline executions, delegating
    to the v2 implementation for actual processing.
    """
    return execute_pipeline_task_v2(
        organization_id=org_schema,
        pipeline_id=pipepline_id,
        pipeline_name=name,
    )


@shared_task(name="execute_pipeline_task_v2", bind=True)
def execute_pipeline_task_v2(
    self,
    organization_id: Any,
    pipeline_id: Any,
    pipeline_name: Any,
) -> None:
    """V2 of execute_pipeline method - worker implementation.

    This method replicates the exact logic from backend/scheduler/tasks.py
    but uses worker clients instead of direct Django ORM access.

    Args:
        organization_id: Organization identifier
        pipeline_id: UID of pipeline entity
        pipeline_name: Pipeline name for logging
    """
    try:
        # Initialize API client with organization context
        api_client = get_singleton_api_client(config)
        api_client.set_organization_context(organization_id)

        logger.info(
            f"Executing scheduled pipeline: {pipeline_id}, "
            f"organization: {organization_id}, pipeline name: {pipeline_name}"
        )

        # Fetch pipeline data via API client with type safety
        try:
            pipeline_response = api_client.get_pipeline_data(
                pipeline_id=pipeline_id, check_active=True
            )

            if not pipeline_response.success:
                logger.error(
                    f"Failed to fetch pipeline {pipeline_id}: {pipeline_response.error}"
                )
                return

            # Parse response using type-safe dataclass
            pipeline_api_data = PipelineApiResponse.from_dict(pipeline_response.data)
            pipeline_data = pipeline_api_data.pipeline

            # Use dataclass properties for type-safe access
            workflow_id = pipeline_data.workflow_id
            pipeline_name_from_api = pipeline_data.pipeline_name

            logger.info(
                f"Found pipeline '{pipeline_name_from_api}' with workflow {workflow_id} "
                f"for pipeline ID {pipeline_id}"
            )

        except Exception as e:
            logger.error(
                f"Error fetching or parsing pipeline data for {pipeline_id}: {e}"
            )
            return

        # Check subscription if validation is enabled
        # Note: In workers, we'll skip subscription validation for now as it requires
        # backend plugins. This can be added later via internal API if needed.
        logger.debug("Skipping subscription validation in worker context")

        # Update pipeline status to INPROGRESS when scheduled execution starts
        try:
            logger.info(
                f"Updating pipeline {pipeline_id} status to {PipelineStatus.INPROGRESS}"
            )
            api_client.update_pipeline_status(
                pipeline_id=pipeline_id,
                status=PipelineStatus.INPROGRESS.value,
                organization_id=organization_id,
            )
            logger.info(
                f"Successfully updated pipeline {pipeline_id} status to {PipelineStatus.INPROGRESS}"
            )
        except Exception as e:
            logger.warning(f"Failed to update pipeline status to INPROGRESS: {e}")
            # Don't fail the entire execution for status update failures

        # Implement scheduler logic directly in worker using type-safe dataclasses
        # This replaces the Django-heavy backend complete_execution method
        try:
            # Create execution context using dataclass
            context = ScheduledPipelineContext(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_name_from_api,
                workflow_id=workflow_id,
                organization_id=organization_id,
                use_file_history=True,  # Always true for scheduled executions
            )

            execution_result = _execute_scheduled_workflow(
                api_client=api_client,
                context=context,
            )

            if execution_result.is_success:
                logger.info(
                    f"[exec:{execution_result.execution_id}] [pipeline:{pipeline_id}] Scheduled execution task dispatched successfully for pipeline '{pipeline_name_from_api}' "
                    f"in organization {organization_id}"
                )
                # Pipeline status will be updated to COMPLETED/FAILED by the actual workflow execution
            else:
                logger.error(
                    f"[exec:{execution_result.execution_id}] [pipeline:{pipeline_id}] Failed to dispatch scheduled execution for pipeline '{pipeline_name_from_api}': {execution_result.error}"
                )
                # Update pipeline status to FAILED since we couldn't even start the execution
                try:
                    api_client.update_pipeline_status(
                        pipeline_id=pipeline_id,
                        status=PipelineStatus.FAILURE.value,
                        organization_id=organization_id,
                    )
                    logger.info(
                        f"Updated pipeline {pipeline_id} status to {PipelineStatus.FAILURE} due to dispatch failure"
                    )
                except Exception as e:
                    logger.warning(f"Failed to update pipeline status to FAILED: {e}")

        except Exception as e:
            logger.error(
                f"Error during scheduled workflow execution for pipeline '{pipeline_name_from_api}': {e}"
            )
            # Update pipeline status to FAILED due to scheduler error
            try:
                api_client.update_pipeline_status(
                    pipeline_id=pipeline_id,
                    status=PipelineStatus.FAILURE.value,
                    organization_id=organization_id,
                )
                logger.info(
                    f"Updated pipeline {pipeline_id} status to {PipelineStatus.FAILURE} due to scheduler exception"
                )
            except Exception as status_error:
                logger.warning(
                    f"Failed to update pipeline status to FAILED: {status_error}"
                )
            raise

    except Exception as e:
        logger.error(
            f"Failed to execute pipeline: {pipeline_name}. Error: {e}"
            f"\n\n'''{traceback.format_exc()}```"
        )

        # Update pipeline status to FAILED for top-level scheduler errors
        try:
            api_client = get_singleton_api_client(config)
            api_client.set_organization_context(
                organization_id if "organization_id" in locals() else None
            )
            if "pipeline_id" in locals() and pipeline_id:
                api_client.update_pipeline_status(
                    pipeline_id=pipeline_id,
                    status=PipelineStatus.FAILURE.value,
                    organization_id=organization_id
                    if "organization_id" in locals()
                    else None,
                )
                logger.info(
                    f"Updated pipeline {pipeline_id} status to {PipelineStatus.FAILURE} due to top-level scheduler error"
                )
        except Exception as status_error:
            logger.warning(
                f"Failed to update pipeline status to FAILED in outer exception: {status_error}"
            )


# Health check task for monitoring
@shared_task(name="scheduler_health_check")
def health_check() -> dict[str, Any]:
    """Health check task for scheduler worker.

    Returns:
        Health status information
    """
    try:
        # Check API client connectivity
        api_client = get_singleton_api_client(config)
        api_status = "healthy" if api_client else "unhealthy"
    except Exception as e:
        api_status = f"unhealthy: {e}"

    return {
        "worker": "scheduler",
        "status": "healthy" if "healthy" in api_status else "degraded",
        "api": api_status,
        "config": {
            "queue": config.queue_name,
            "organization_id": config.organization_id,
        },
    }
