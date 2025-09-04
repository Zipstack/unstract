"""Tool API Client for Tool Execution Operations

This module provides specialized API client for tool execution operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Tool instance execution
- Tool execution status tracking
- Tool instance management
- Tool workflow integration
- Tool result handling
"""

import logging
import uuid
from typing import Any

from ..data.models import (
    APIResponse,
    BatchOperationRequest,
    BatchOperationResponse,
)
from ..enums import BatchOperationType, LogLevel, TaskStatus
from ..utils.retry_temp import CircuitBreakerOpenError, circuit_breaker
from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ToolAPIClient(BaseAPIClient):
    """Specialized API client for tool execution operations.

    This client handles all tool-related operations including:
    - Executing tool instances
    - Tracking tool execution status
    - Managing tool instances
    - Tool workflow integration
    - Tool result processing
    """

    def execute_tool(
        self,
        tool_instance_id: str | uuid.UUID,
        input_data: dict[str, Any],
        file_data: dict[str, Any] | None = None,
        execution_context: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Execute a tool instance with provided data.

        Args:
            tool_instance_id: Tool instance ID to execute
            input_data: Input data for the tool execution
            file_data: Optional file data for processing
            execution_context: Optional execution context
            organization_id: Optional organization ID override

        Returns:
            Tool execution result
        """
        data = {
            "input_data": input_data,
            "file_data": file_data or {},
            "execution_context": execution_context or {},
        }

        logger.info(f"Executing tool {tool_instance_id} with input data: {input_data}")
        logger.debug(f"Tool execution context: {execution_context}")

        try:
            response = self.post(
                self._build_url("tool_execution", f"{str(tool_instance_id)}/execute/"),
                data,
                organization_id=organization_id,
            )

            execution_id = response.get("execution_id", "unknown")
            logger.info(
                f"Successfully started tool execution {execution_id} for tool {tool_instance_id}"
            )
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(f"Failed to execute tool {tool_instance_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_tool_execution_status(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get tool execution status by execution ID.

        Args:
            execution_id: Tool execution ID
            organization_id: Optional organization ID override

        Returns:
            Tool execution status information
        """
        logger.debug(f"Getting tool execution status for {execution_id}")

        try:
            response = self.get(
                self._build_url("tool_execution", f"status/{str(execution_id)}/"),
                organization_id=organization_id,
            )

            status = response.get("status", "unknown")
            logger.debug(f"Tool execution {execution_id} status: {status}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(
                f"Failed to get tool execution status for {execution_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))

    def get_tool_instances_by_workflow(
        self, workflow_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get tool instances for a specific workflow.

        Args:
            workflow_id: Workflow ID
            organization_id: Optional organization ID override

        Returns:
            List of tool instances for the workflow
        """
        logger.debug(f"Getting tool instances for workflow {workflow_id}")

        try:
            response = self.get(
                self._build_url(
                    "tool_execution", f"workflow/{str(workflow_id)}/instances/"
                ),
                organization_id=organization_id,
            )

            instance_count = len(response.get("instances", []))
            logger.debug(
                f"Retrieved {instance_count} tool instances for workflow {workflow_id}"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(
                f"Failed to get tool instances for workflow {workflow_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))

    def get_tool_instance_details(
        self, tool_instance_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get detailed information about a tool instance.

        Args:
            tool_instance_id: Tool instance ID
            organization_id: Optional organization ID override

        Returns:
            Tool instance details
        """
        logger.debug(f"Getting tool instance details for {tool_instance_id}")

        try:
            response = self.get(
                self._build_url("tool_execution", f"instance/{str(tool_instance_id)}/"),
                organization_id=organization_id,
            )

            tool_name = response.get("tool_name", "unknown")
            logger.debug(
                f"Retrieved tool instance details for {tool_name} ({tool_instance_id})"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(
                f"Failed to get tool instance details for {tool_instance_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))

    def get_tool_execution_result(
        self, execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> APIResponse:
        """Get tool execution result by execution ID.

        Args:
            execution_id: Tool execution ID
            organization_id: Optional organization ID override

        Returns:
            Tool execution result data
        """
        logger.debug(f"Getting tool execution result for {execution_id}")

        try:
            response = self.get(
                self._build_url("tool_execution", f"result/{str(execution_id)}/"),
                organization_id=organization_id,
            )

            logger.debug(f"Retrieved tool execution result for {execution_id}")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(
                f"Failed to get tool execution result for {execution_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))

    def get_tool_execution_logs(
        self,
        execution_id: str | uuid.UUID,
        level: str | LogLevel | None = None,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get tool execution logs.

        Args:
            execution_id: Tool execution ID
            level: Log level filter (DEBUG, INFO, WARNING, ERROR)
            limit: Maximum number of log entries to return
            organization_id: Optional organization ID override

        Returns:
            Tool execution logs
        """
        # Convert level to string if it's an enum
        level_str = level.value if isinstance(level, LogLevel) else level

        params = {"limit": limit}
        if level_str:
            params["level"] = level_str

        logger.debug(f"Getting tool execution logs for {execution_id}")

        try:
            response = self.get(
                self._build_url("tool_execution", f"logs/{str(execution_id)}/"),
                params=params,
                organization_id=organization_id,
            )

            log_count = len(response.get("logs", []))
            logger.debug(
                f"Retrieved {log_count} log entries for tool execution {execution_id}"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(
                f"Failed to get tool execution logs for {execution_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))

    @circuit_breaker(failure_threshold=3, recovery_timeout=60.0)
    def cancel_tool_execution(
        self,
        execution_id: str | uuid.UUID,
        reason: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Cancel a running tool execution.

        Args:
            execution_id: Tool execution ID to cancel
            reason: Optional cancellation reason
            organization_id: Optional organization ID override

        Returns:
            Cancellation response
        """
        data = {"execution_id": str(execution_id)}
        if reason:
            data["reason"] = reason

        logger.info(f"Cancelling tool execution {execution_id}")

        try:
            response = self.post(
                self._build_url("tool_execution", f"cancel/{str(execution_id)}/"),
                data,
                organization_id=organization_id,
            )

            logger.info(f"Successfully cancelled tool execution {execution_id}")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except CircuitBreakerOpenError:
            logger.warning(
                f"Tool execution cancellation circuit breaker open for {execution_id}"
            )
            return APIResponse(
                success=False,
                error="Circuit breaker open - tool cancellation service unavailable",
            )
        except Exception as e:
            logger.error(f"Failed to cancel tool execution {execution_id}: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def batch_execute_tools(
        self, tool_executions: list[dict[str, Any]], organization_id: str | None = None
    ) -> BatchOperationResponse:
        """Execute multiple tools in a single batch request.

        Args:
            tool_executions: List of tool execution configurations
            organization_id: Optional organization ID override

        Returns:
            BatchOperationResponse with execution results
        """
        batch_request = BatchOperationRequest(
            operation_type=BatchOperationType.CREATE,
            items=tool_executions,
            organization_id=organization_id,
        )

        logger.info(f"Batch executing {len(tool_executions)} tools")

        try:
            response = self.post(
                self._build_url("tool_execution", "batch-execute/"),
                batch_request.to_dict(),
                organization_id=organization_id,
            )

            successful = response.get("successful", 0)
            failed = response.get("failed", 0)
            logger.info(
                f"Batch tool execution completed: {successful} successful, {failed} failed"
            )

            return BatchOperationResponse(
                operation_id=response.get("operation_id", str(uuid.uuid4())),
                total_items=len(tool_executions),
                successful_items=successful,
                failed_items=failed,
                status=TaskStatus(response.get("status", TaskStatus.SUCCESS.value)),
                results=response.get("results", []),
                errors=response.get("errors", []),
                execution_time=response.get("execution_time"),
            )

        except Exception as e:
            logger.error(f"Failed to batch execute tools: {str(e)}")
            return BatchOperationResponse(
                operation_id=str(uuid.uuid4()),
                total_items=len(tool_executions),
                successful_items=0,
                failed_items=len(tool_executions),
                status=TaskStatus.FAILURE,
                results=[],
                errors=[{"error": str(e)}],
            )

    def get_tool_execution_history(
        self,
        tool_instance_id: str | uuid.UUID | None = None,
        workflow_id: str | uuid.UUID | None = None,
        status: str | TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get tool execution history with filtering options.

        Args:
            tool_instance_id: Filter by tool instance ID
            workflow_id: Filter by workflow ID
            status: Filter by execution status
            limit: Maximum number of records to return
            offset: Number of records to skip
            organization_id: Optional organization ID override

        Returns:
            Paginated tool execution history
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        params = {"limit": limit, "offset": offset}

        if tool_instance_id:
            params["tool_instance_id"] = str(tool_instance_id)
        if workflow_id:
            params["workflow_id"] = str(workflow_id)
        if status_str:
            params["status"] = status_str

        logger.debug(f"Getting tool execution history with filters: {params}")

        try:
            response = self.get(
                self._build_url("tool_execution", "history/"),
                params=params,
                organization_id=organization_id,
            )

            count = response.get("count", 0)
            logger.debug(f"Retrieved {count} tool execution history records")
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get tool execution history: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def get_tool_execution_metrics(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        tool_instance_id: str | uuid.UUID | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Get tool execution metrics and statistics.

        Args:
            start_date: Start date for metrics (ISO format)
            end_date: End date for metrics (ISO format)
            tool_instance_id: Optional tool instance ID filter
            organization_id: Optional organization ID override

        Returns:
            Tool execution metrics
        """
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if tool_instance_id:
            params["tool_instance_id"] = str(tool_instance_id)

        logger.debug(
            f"Getting tool execution metrics for date range: {start_date} to {end_date}"
        )

        try:
            response = self.get(
                self._build_url("tool_execution", "metrics/"),
                params=params,
                organization_id=organization_id,
            )

            total_executions = response.get("total_executions", 0)
            success_rate = response.get("success_rate", 0.0)
            logger.debug(
                f"Tool execution metrics: {total_executions} executions, {success_rate:.1%} success rate"
            )
            return APIResponse(success=True, data=response, status_code=200)

        except Exception as e:
            logger.error(f"Failed to get tool execution metrics: {str(e)}")
            return APIResponse(success=False, error=str(e))

    def update_tool_execution_status(
        self,
        execution_id: str | uuid.UUID,
        status: str | TaskStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        organization_id: str | None = None,
    ) -> APIResponse:
        """Update tool execution status and result.

        Args:
            execution_id: Tool execution ID
            status: New execution status
            result: Optional execution result data
            error_message: Optional error message
            organization_id: Optional organization ID override

        Returns:
            Update response
        """
        # Convert status to string if it's an enum
        status_str = status.value if isinstance(status, TaskStatus) else status

        data = {"status": status_str}

        if result is not None:
            data["result"] = result
        if error_message is not None:
            data["error_message"] = error_message

        logger.info(f"Updating tool execution {execution_id} status to {status_str}")

        try:
            response = self.post(
                self._build_url("tool_execution", f"status/{str(execution_id)}/update/"),
                data,
                organization_id=organization_id,
            )

            logger.info(f"Successfully updated tool execution {execution_id} status")
            return APIResponse(
                success=response.get("success", True),
                data=response,
                status_code=response.get("status_code"),
            )

        except Exception as e:
            logger.error(
                f"Failed to update tool execution status for {execution_id}: {str(e)}"
            )
            return APIResponse(success=False, error=str(e))
