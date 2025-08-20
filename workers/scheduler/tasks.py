"""Scheduler Worker Tasks

This worker handles scheduled pipeline executions, migrated from @backend/scheduler/tasks.py
to support the new workers architecture while maintaining backward compatibility.
"""

import traceback
from typing import Any

from celery import shared_task
from shared.api_client_singleton import get_singleton_api_client
from shared.config import WorkerConfig
from shared.logging_utils import WorkerLogger
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
        execution_request = WorkflowExecutionRequest(
            workflow_id=context.workflow_id,
            pipeline_id=context.pipeline_id,
            organization_id=context.organization_id,
            single_step=False,
            mode=ExecutionMode.QUEUE,
            total_files=0,  # Will be updated during execution
            scheduled=True,
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
            f"Created workflow execution {execution_id} for scheduled pipeline {context.pipeline_name}"
        )

        # Step 2: Trigger async workflow execution via direct Celery dispatch
        logger.info(
            f"Triggering async execution for workflow {context.workflow_id}, execution {execution_id}"
        )

        # Use Celery to dispatch async execution task directly (like backend scheduler does)
        from celery import current_app

        logger.info(f"Dispatching async_execute_bin task for execution {execution_id}")

        try:
            # Dispatch the Celery task directly to the general queue
            async_result = current_app.send_task(
                "async_execute_bin",
                args=[
                    context.organization_id,  # schema_name (organization_id)
                    context.workflow_id,  # workflow_id
                    execution_id,  # execution_id
                    {},  # hash_values_of_files (empty for scheduled)
                    context.use_file_history,  # use_file_history
                ],
                kwargs={},
                queue="celery",  # Route to celery queue (what general worker listens to)
            )

            task_id = async_result.id
            logger.info(
                f"Successfully dispatched async_execute_bin task {task_id} for execution {execution_id}"
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

        # For scheduler tasks, we skip the initial pipeline status update to INPROGRESS
        # because we don't have an execution_id yet. The workflow execution will handle this.
        logger.debug(
            "Skipping initial pipeline status update - will be handled by workflow execution"
        )

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
                    f"Scheduled execution {execution_result.execution_id} completed for pipeline '{pipeline_name_from_api}' "
                    f"in organization {organization_id}"
                )
            else:
                logger.error(
                    f"Scheduled execution failed for pipeline '{pipeline_name_from_api}': {execution_result.error}"
                )

        except Exception as e:
            logger.error(
                f"Error during scheduled workflow execution for pipeline '{pipeline_name_from_api}': {e}"
            )
            raise

    except Exception as e:
        logger.error(
            f"Failed to execute pipeline: {pipeline_name}. Error: {e}"
            f"\n\n'''{traceback.format_exc()}```"
        )

        # For scheduler tasks, we skip the error status update
        # because we don't have an execution_id. The workflow execution handles status.
        logger.debug(
            "Skipping pipeline error status update - handled by workflow execution"
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
