"""Tool Validation Utilities

Shared validation logic for tool instances before workflow execution.
This module provides common validation functionality used by both general
and API deployment workers to eliminate code duplication.
"""

import logging

from shared.api.internal_client import InternalAPIClient
from shared.infrastructure.logging.workflow_logger import WorkerWorkflowLogger

from unstract.core.data_models import ExecutionStatus

logger = logging.getLogger(__name__)


def validate_workflow_tool_instances(
    api_client: InternalAPIClient,
    workflow_id: str,
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None = None,
    workflow_type: str = "general",
) -> None:
    """Validate tool instances for a workflow before execution begins.

    This function performs comprehensive validation of tool instances including:
    1. Adapter name to ID migration
    2. User permissions validation
    3. Tool settings JSON schema validation

    Args:
        api_client: Internal API client instance
        workflow_id: Workflow ID to validate tools for
        execution_id: Execution ID for logging and status updates
        organization_id: Organization ID for scoped operations
        pipeline_id: Pipeline ID (optional, for logging context)
        workflow_type: Type of workflow for logging context ("general" or "api")

    Raises:
        Exception: If tool validation fails or API calls fail

    Note:
        This function updates workflow execution status to ERROR on validation failures
        and provides comprehensive logging to both application logs and UI via WorkerWorkflowLogger.
    """
    # Get tool instances via separate API call (execution context doesn't include them)
    tool_instances_response = api_client.get_tool_instances_by_workflow(
        workflow_id=workflow_id, organization_id=organization_id
    )
    tool_instances_data = tool_instances_response.tool_instances

    if not tool_instances_data:
        logger.info(
            f"No tool instances data available for validation in {workflow_type} workflow {workflow_id}"
        )
        return

    logger.info(
        f"Validating {len(tool_instances_data)} tool instances for {workflow_type} workflow {workflow_id}"
    )

    # Extract tool instance IDs for validation
    tool_instance_ids = [
        tool_data.get("id") for tool_data in tool_instances_data if tool_data.get("id")
    ]

    if not tool_instance_ids:
        logger.info(
            f"No tool instances found to validate for {workflow_type} workflow {workflow_id}"
        )
        return

    # Create workflow-specific logger for UI feedback
    workflow_logger = _create_workflow_logger(
        workflow_type=workflow_type,
        execution_id=execution_id,
        organization_id=organization_id,
        pipeline_id=pipeline_id,
    )

    try:
        # Call backend validation API
        validation_response = api_client.validate_tool_instances(
            workflow_id=workflow_id,
            tool_instance_ids=tool_instance_ids,
            organization_id=organization_id,
        )

        if not validation_response.get("success", False):
            # Validation failed - extract error details
            errors = validation_response.get("errors", [])
            error_details = "; ".join(
                [
                    f"{err.get('tool_id', 'unknown')}: {err.get('error', 'unknown error')}"
                    for err in errors
                ]
            )
            error_msg = f"Tool instance validation failed: {error_details}"

            logger.error(
                f"{workflow_type.title()} workflow validation failed for {execution_id}: {error_msg}"
            )

            # Log validation failure to UI
            if workflow_logger:
                workflow_logger.log_error(
                    logger, f"❌ Tool validation failed: {error_details}"
                )

            # Update execution status to ERROR and exit early
            api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=ExecutionStatus.ERROR.value,
                error_message=error_msg,
            )

            raise Exception(error_msg)

        else:
            # Validation succeeded
            context_suffix = "API workflow" if workflow_type == "api" else "workflow"
            logger.info(
                f"Successfully validated {len(tool_instance_ids)} tool instances for {context_suffix}"
            )

            # Log validation success to UI
            if workflow_logger:
                workflow_logger.log_info(
                    logger,
                    f"✅ Validated {len(tool_instance_ids)} tool instances successfully",
                )

    except Exception as validation_error:
        # Handle API call failures or other exceptions
        logger.error(
            f"Tool validation API call failed for {workflow_type} workflow {execution_id}: {validation_error}"
        )

        # Log API failure to UI
        if workflow_logger:
            workflow_logger.log_error(
                logger, f"❌ Tool validation API call failed: {str(validation_error)}"
            )

        # Update execution status and re-raise
        api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.ERROR.value,
            error_message=f"Tool validation failed: {str(validation_error)}",
        )
        raise


def _create_workflow_logger(
    workflow_type: str,
    execution_id: str,
    organization_id: str,
    pipeline_id: str | None = None,
) -> WorkerWorkflowLogger | None:
    """Create appropriate workflow logger based on workflow type.

    Args:
        workflow_type: Type of workflow ("general" or "api")
        execution_id: Execution ID for logger context
        organization_id: Organization ID for logger context
        pipeline_id: Pipeline ID for logger context (optional)

    Returns:
        WorkerWorkflowLogger instance or None if creation fails
    """
    try:
        if workflow_type == "api":
            return WorkerWorkflowLogger.create_for_api_workflow(
                execution_id=execution_id,
                organization_id=organization_id,
                pipeline_id=pipeline_id,
            )
        else:
            return WorkerWorkflowLogger.create_for_general_workflow(
                execution_id=execution_id,
                organization_id=organization_id,
                pipeline_id=pipeline_id,
            )
    except Exception as logger_error:
        logger.warning(f"Failed to create workflow logger: {logger_error}")
        return None
