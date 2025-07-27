"""Worker-Native Workflow Orchestrator

This module provides worker-native workflow execution orchestration without backend dependency.
Replaces backend-heavy workflow execution logic with worker-native processing and database checkpoints.
"""

import time
from typing import Any

# Import shared data models
from unstract.core.data_models import ExecutionStatus, FileHashData
from unstract.workflow_execution.dto import ToolInstance, WorkflowDto
from unstract.workflow_execution.enums import ExecutionType

# Import workflow execution service
from unstract.workflow_execution.workflow_execution import WorkflowExecutionService

from .api_client import InternalAPIClient

# Import worker infrastructure
from .logging_utils import WorkerLogger
from .retry_utils import circuit_breaker, retry

logger = WorkerLogger.get_logger(__name__)


class WorkerWorkflowOrchestrator:
    """Orchestrates workflow execution within workers using database checkpoints"""

    def __init__(self, api_client: InternalAPIClient):
        """Initialize orchestrator with API client for database operations only.

        Args:
            api_client: API client for database operations
        """
        self.api_client = api_client  # Database operations only
        self.workflow_service = WorkflowExecutionService()

    @retry(max_attempts=3, base_delay=2.0)
    @circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
    def execute_workflow_file(
        self,
        file_data: FileHashData,
        workflow_config: dict[str, Any],
        execution_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute workflow for single file with database checkpoints.

        This replaces backend workflow execution with worker-native processing
        while maintaining database consistency through checkpoints.

        Args:
            file_data: FileHashData object with file information
            workflow_config: Workflow configuration with tools and settings
            execution_context: Execution context with IDs and metadata

        Returns:
            Dictionary with execution results

        Raises:
            RuntimeError: If workflow execution fails
        """
        workflow_id = execution_context["workflow_id"]
        execution_id = execution_context["execution_id"]
        organization_id = execution_context["organization_id"]

        logger.info(
            f"Executing workflow for file {file_data.file_name} (workflow: {workflow_id})"
        )

        # Create file execution record via database API
        file_execution_data = {
            "workflow_execution_id": execution_id,
            "file_name": file_data.file_name,
            "file_path": file_data.file_path,
            "file_hash": file_data.file_hash,
            "provider_file_uuid": file_data.provider_file_uuid,
            "mime_type": file_data.mime_type,
            "file_size": file_data.file_size,
            "status": ExecutionStatus.EXECUTING.value,
        }

        try:
            file_execution = self.api_client.create_file_execution(file_execution_data)
            file_execution_id = file_execution["id"]

            logger.debug(f"Created file execution record: {file_execution_id}")

        except Exception as e:
            error_msg = f"Failed to create file execution record: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        execution_start_time = time.time()

        try:
            # Checkpoint: File processing started
            self._checkpoint_progress(
                file_execution_id,
                "PROCESSING_STARTED",
                ExecutionStatus.EXECUTING.value,
                {"start_time": execution_start_time},
            )

            # Prepare workflow DTO for execution service
            workflow_dto = self._prepare_workflow_dto(
                workflow_config=workflow_config, execution_context=execution_context
            )

            # Execute workflow using workflow-execution service (worker-native)
            workflow_result = self.workflow_service.execute_workflow(
                workflow_dto=workflow_dto,
                input_file_path=file_data.file_path,
                execution_type=ExecutionType.SINGLE_FILE,
                organization_id=organization_id,
            )

            execution_time = time.time() - execution_start_time

            # Checkpoint: File processing completed
            self._checkpoint_progress(
                file_execution_id,
                "PROCESSING_COMPLETED",
                ExecutionStatus.COMPLETED.value,
                {
                    "result": workflow_result,
                    "execution_time": execution_time,
                    "end_time": time.time(),
                },
            )

            logger.info(
                f"Successfully executed workflow for {file_data.file_name} in {execution_time:.2f}s"
            )

            return {
                "status": "success",
                "file_execution_id": file_execution_id,
                "file_name": file_data.file_name,
                "execution_time": execution_time,
                "result": workflow_result,
            }

        except Exception as e:
            execution_time = time.time() - execution_start_time
            error_msg = f"Workflow execution failed for {file_data.file_name}: {str(e)}"

            # Checkpoint: File processing failed
            self._checkpoint_progress(
                file_execution_id,
                "PROCESSING_FAILED",
                ExecutionStatus.ERROR.value,
                {
                    "error": str(e),
                    "execution_time": execution_time,
                    "end_time": time.time(),
                },
            )

            logger.error(error_msg, exc_info=True)

            return {
                "status": "error",
                "file_execution_id": file_execution_id,
                "file_name": file_data.file_name,
                "execution_time": execution_time,
                "error": str(e),
            }

    def execute_workflow_batch(
        self,
        files: list[FileHashData],
        workflow_config: dict[str, Any],
        execution_context: dict[str, Any],
        max_concurrent: int = 3,
    ) -> dict[str, Any]:
        """Execute workflow for multiple files with controlled concurrency.

        Args:
            files: List of FileHashData objects
            workflow_config: Workflow configuration
            execution_context: Execution context
            max_concurrent: Maximum concurrent file processing

        Returns:
            Dictionary with batch execution results
        """
        logger.info(
            f"Executing workflow batch for {len(files)} files (max concurrent: {max_concurrent})"
        )

        batch_start_time = time.time()
        successful_files = 0
        failed_files = 0
        file_results = []

        # Process files sequentially for now (can be enhanced with asyncio for concurrency)
        for file_data in files:
            try:
                file_result = self.execute_workflow_file(
                    file_data=file_data,
                    workflow_config=workflow_config,
                    execution_context=execution_context,
                )

                if file_result["status"] == "success":
                    successful_files += 1
                else:
                    failed_files += 1

                file_results.append(file_result)

            except Exception as e:
                failed_files += 1
                file_results.append(
                    {
                        "status": "error",
                        "file_name": file_data.file_name,
                        "error": str(e),
                        "execution_time": 0,
                    }
                )
                logger.error(
                    f"Batch file processing failed for {file_data.file_name}: {str(e)}"
                )

        batch_execution_time = time.time() - batch_start_time

        batch_result = {
            "total_files": len(files),
            "successful_files": successful_files,
            "failed_files": failed_files,
            "batch_execution_time": batch_execution_time,
            "file_results": file_results,
        }

        logger.info(
            f"Batch execution complete: {successful_files}/{len(files)} successful "
            f"in {batch_execution_time:.2f}s"
        )

        return batch_result

    def _checkpoint_progress(
        self,
        file_execution_id: str,
        stage: str,
        status: str,
        metadata: dict | None = None,
    ) -> bool:
        """Database checkpoint via API client - keeps backend informed.

        Args:
            file_execution_id: File execution ID
            stage: Processing stage name
            status: Execution status
            metadata: Additional metadata (optional)

        Returns:
            True if checkpoint successful, False otherwise
        """
        try:
            checkpoint_data = {
                "status": status,
                "metadata": metadata or {},
                "stage": stage,
                "checkpoint_time": time.time(),
            }

            # Update file execution via database API
            success = self.api_client.update_file_execution_status(
                file_execution_id=file_execution_id, **checkpoint_data
            )

            logger.debug(
                f"Checkpoint {stage} for file execution {file_execution_id}: {'success' if success else 'failed'}"
            )
            return success

        except Exception as e:
            logger.error(
                f"Failed to checkpoint progress for {file_execution_id}: {str(e)}"
            )
            return False

    def _prepare_workflow_dto(
        self, workflow_config: dict[str, Any], execution_context: dict[str, Any]
    ) -> WorkflowDto:
        """Prepare WorkflowDto from configuration for execution service.

        Args:
            workflow_config: Workflow configuration
            execution_context: Execution context

        Returns:
            WorkflowDto object for execution service
        """
        # Extract tools configuration
        tools_config = workflow_config.get("tools", [])

        # Convert tools config to ToolInstance objects
        tool_instances = []
        for tool_config in tools_config:
            tool_instance = ToolInstance(
                tool_id=tool_config.get("tool_id"),
                tool_name=tool_config.get("tool_name", ""),
                tool_settings=tool_config.get("settings", {}),
                step_name=tool_config.get("step_name", ""),
                prompt_registry_id=tool_config.get("prompt_registry_id"),
                enable=tool_config.get("enable", True),
            )
            tool_instances.append(tool_instance)

        # Create workflow DTO
        workflow_dto = WorkflowDto(
            workflow_id=execution_context["workflow_id"],
            workflow_name=workflow_config.get("workflow_name", ""),
            tool_instances=tool_instances,
            organization_id=execution_context["organization_id"],
            execution_id=execution_context["execution_id"],
        )

        logger.debug(f"Prepared workflow DTO with {len(tool_instances)} tools")
        return workflow_dto

    def get_execution_summary(
        self, execution_id: str, organization_id: str
    ) -> dict[str, Any]:
        """Get execution summary via database API.

        Args:
            execution_id: Execution ID
            organization_id: Organization ID

        Returns:
            Dictionary with execution summary
        """
        try:
            # Get execution context via database API
            execution_context = self.api_client.get_workflow_execution(
                execution_id=execution_id, organization_id=organization_id
            )

            # Get file executions for this workflow execution
            file_executions = self.api_client.get_file_executions_for_execution(
                execution_id=execution_id, organization_id=organization_id
            )

            # Calculate summary statistics
            total_files = len(file_executions)
            completed_files = sum(
                1 for fe in file_executions if fe.get("status") == "COMPLETED"
            )
            failed_files = sum(1 for fe in file_executions if fe.get("status") == "ERROR")
            processing_files = sum(
                1 for fe in file_executions if fe.get("status") == "EXECUTING"
            )

            summary = {
                "execution_id": execution_id,
                "workflow_id": execution_context.get("workflow_id"),
                "status": execution_context.get("status"),
                "total_files": total_files,
                "completed_files": completed_files,
                "failed_files": failed_files,
                "processing_files": processing_files,
                "success_rate": (completed_files / total_files * 100)
                if total_files > 0
                else 0,
                "file_executions": file_executions,
            }

            logger.debug(
                f"Generated execution summary for {execution_id}: {completed_files}/{total_files} completed"
            )
            return summary

        except Exception as e:
            error_msg = f"Failed to get execution summary for {execution_id}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


class WorkerWorkflowExecutionManager:
    """Manage complete workflow executions using worker-native operations"""

    def __init__(self, api_client: InternalAPIClient):
        """Initialize execution manager.

        Args:
            api_client: API client for database operations
        """
        self.api_client = api_client
        self.orchestrator = WorkerWorkflowOrchestrator(api_client)

    def execute_complete_workflow(
        self,
        workflow_id: str,
        execution_id: str,
        organization_id: str,
        source_files: list[FileHashData],
        workflow_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute complete workflow with all files.

        Args:
            workflow_id: Workflow ID
            execution_id: Execution ID
            organization_id: Organization ID
            source_files: List of source files to process
            workflow_config: Workflow configuration

        Returns:
            Dictionary with complete execution results
        """
        logger.info(
            f"Starting complete workflow execution {execution_id} with {len(source_files)} files"
        )

        execution_context = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "organization_id": organization_id,
        }

        workflow_start_time = time.time()

        try:
            # Update execution status to processing
            self.api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=ExecutionStatus.EXECUTING.value,
                metadata={"total_files": len(source_files)},
            )

            # Execute workflow for all files
            batch_result = self.orchestrator.execute_workflow_batch(
                files=source_files,
                workflow_config=workflow_config,
                execution_context=execution_context,
            )

            workflow_execution_time = time.time() - workflow_start_time

            # Determine final status
            if batch_result["failed_files"] == 0:
                final_status = ExecutionStatus.COMPLETED.value
            elif batch_result["successful_files"] > 0:
                final_status = (
                    ExecutionStatus.COMPLETED.value
                )  # Partial success still counts as completed
            else:
                final_status = ExecutionStatus.ERROR.value

            # Update final execution status
            self.api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=final_status,
                metadata={
                    "total_files": batch_result["total_files"],
                    "successful_files": batch_result["successful_files"],
                    "failed_files": batch_result["failed_files"],
                    "execution_time": workflow_execution_time,
                },
            )

            execution_result = {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "status": final_status,
                "execution_time": workflow_execution_time,
                "batch_result": batch_result,
            }

            logger.info(
                f"Complete workflow execution finished: {batch_result['successful_files']}/{batch_result['total_files']} "
                f"successful in {workflow_execution_time:.2f}s"
            )

            return execution_result

        except Exception as e:
            # Mark execution as failed
            self.api_client.update_workflow_execution_status(
                execution_id=execution_id,
                status=ExecutionStatus.ERROR.value,
                metadata={"error": str(e)},
            )

            error_msg = f"Complete workflow execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def retry_failed_files(
        self, execution_id: str, organization_id: str, workflow_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Retry execution for failed files only.

        Args:
            execution_id: Execution ID
            organization_id: Organization ID
            workflow_config: Workflow configuration

        Returns:
            Dictionary with retry results
        """
        logger.info(f"Retrying failed files for execution {execution_id}")

        try:
            # Get execution summary to find failed files
            execution_summary = self.orchestrator.get_execution_summary(
                execution_id=execution_id, organization_id=organization_id
            )

            # Filter failed file executions
            failed_file_executions = [
                fe
                for fe in execution_summary["file_executions"]
                if fe.get("status") == "ERROR"
            ]

            if not failed_file_executions:
                logger.info(f"No failed files found for execution {execution_id}")
                return {"retry_count": 0, "message": "No failed files to retry"}

            # Convert failed file executions back to FileHashData
            failed_files = []
            for fe in failed_file_executions:
                file_data = FileHashData(
                    file_name=fe.get("file_name", ""),
                    file_path=fe.get("file_path", ""),
                    file_hash=fe.get("file_hash", ""),
                    provider_file_uuid=fe.get("provider_file_uuid"),
                    file_size=fe.get("file_size", 0),
                    mime_type=fe.get("mime_type", ""),
                )
                failed_files.append(file_data)

            # Retry execution for failed files
            execution_context = {
                "workflow_id": execution_summary["workflow_id"],
                "execution_id": execution_id,
                "organization_id": organization_id,
            }

            retry_result = self.orchestrator.execute_workflow_batch(
                files=failed_files,
                workflow_config=workflow_config,
                execution_context=execution_context,
            )

            logger.info(
                f"Retry completed: {retry_result['successful_files']}/{len(failed_files)} files recovered"
            )

            return {"retry_count": len(failed_files), "retry_result": retry_result}

        except Exception as e:
            error_msg = f"Failed file retry failed for execution {execution_id}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
