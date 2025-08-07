"""Worker-based Workflow Execution Service

This module contains the migrated business logic from Django's WorkflowExecutionServiceHelper
to workers. It coordinates workflow execution through internal APIs instead of direct DB access.
"""

from typing import Any

from unstract.core.data_models import ExecutionStatus, FileHash
from unstract.workflow_execution import WorkflowExecutionService
from unstract.workflow_execution.dto import ToolInstance as ToolInstanceDto
from unstract.workflow_execution.dto import WorkflowDto

from .api_client import InternalAPIClient
from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkerWorkflowExecutionService(WorkflowExecutionService):
    """Worker-based workflow execution service.

    This replaces Django's WorkflowExecutionServiceHelper by:
    1. Using internal APIs instead of direct DB access
    2. Handling all business logic in workers
    3. Maintaining exact same execution patterns as backend
    """

    def __init__(
        self,
        api_client: InternalAPIClient,
        workflow_id: str,
        organization_id: str,
        pipeline_id: str | None = None,
        single_step: bool = False,
        scheduled: bool = False,
        mode: tuple[str, str] = ("INSTANT", "INSTANT"),  # Default mode
        execution_id: str | None = None,
        use_file_history: bool = True,
        file_execution_id: str | None = None,
    ):
        """Initialize worker workflow execution service.

        Args:
            api_client: Internal API client for backend communication
            workflow_id: Workflow ID
            organization_id: Organization ID
            pipeline_id: Optional pipeline ID
            single_step: Whether to execute single step
            scheduled: Whether execution is scheduled
            mode: Execution mode tuple
            execution_id: Optional existing execution ID
            use_file_history: Whether to use file history
            file_execution_id: Optional file execution ID
        """
        self.api_client = api_client
        self.workflow_id = workflow_id
        self.organization_id = organization_id
        self.pipeline_id = pipeline_id
        self.single_step = single_step
        self.scheduled = scheduled
        self.mode = mode
        self.execution_id = execution_id
        self.use_file_history = use_file_history
        self.file_execution_id = file_execution_id

        # Get workflow and tool instances from backend
        self.workflow_data = self._get_workflow_data()
        self.tool_instances_data = self._get_tool_instances_data()

        # Convert to DTOs
        workflow_dto = self._convert_workflow_to_dto(self.workflow_data)
        tool_instance_dtos = self._convert_tool_instances_to_dtos(
            self.tool_instances_data
        )

        # Get platform service API key
        platform_service_api_key = self._get_platform_service_api_key(organization_id)

        # Initialize parent WorkflowExecutionService
        super().__init__(
            organization_id=organization_id,
            workflow_id=workflow_id,
            workflow=workflow_dto,
            tool_instances=tool_instance_dtos,
            platform_service_api_key=platform_service_api_key,
            ignore_processed_entities=False,
            file_execution_id=file_execution_id,
        )

        # Restore execution_id (parent constructor overwrites it with empty string)
        self.execution_id = execution_id

        # Set execution context
        self.execution_log_id = pipeline_id  # Use pipeline_id for logging
        self.project_settings = {"WF_PROJECT_GUID": str(self.execution_log_id)}

        # Set messaging channel for real-time updates
        self.set_messaging_channel(str(self.execution_log_id))

        logger.info(
            f"Initialized worker workflow execution service - "
            f"Pipeline ID: {pipeline_id}, Workflow ID: {workflow_id}, "
            f"Execution ID: {execution_id}, Organization: {organization_id}"
        )

    def _get_platform_service_api_key(self, organization_id: str) -> str:
        """Get platform service API key from backend API.

        Args:
            organization_id: Organization ID

        Returns:
            Platform service API key
        """
        try:
            # Call the internal API to get the platform key using X-Organization-ID header
            response = self.api_client._make_request(
                method="GET",
                endpoint="v1/platform-settings/platform-key/",
                organization_id=organization_id,  # This will be passed as X-Organization-ID header
            )

            if response and "platform_key" in response:
                logger.info(
                    f"Successfully retrieved platform key for org {organization_id}"
                )
                return response["platform_key"]
            else:
                logger.error(
                    f"No platform key found for org {organization_id} in API response"
                )
                raise Exception(
                    f"No active platform key found for organization {organization_id}"
                )

        except Exception as e:
            logger.error(
                f"Failed to get platform key from API for org {organization_id}: {e}"
            )
            raise Exception(
                f"Unable to retrieve platform service API key for organization {organization_id}: {e}"
            )

    def _get_workflow_data(self) -> dict[str, Any]:
        """Get workflow data from backend API.

        Returns:
            Workflow data dictionary
        """
        try:
            response = self.api_client.get_workflow_execution(self.execution_id)
            if not response.success:
                raise Exception(f"Failed to get workflow execution: {response.error}")
            return response.data.get("workflow", {})
        except Exception as e:
            logger.error(f"Failed to get workflow data: {e}")
            raise

    def _get_tool_instances_data(self) -> list[dict[str, Any]]:
        """Get tool instances data from backend API.

        Returns:
            List of tool instance data dictionaries
        """
        try:
            response = self.api_client.get_tool_instances_by_workflow(
                workflow_id=self.workflow_id,
                organization_id=self.organization_id,
            )
            return response.get("tool_instances", [])
        except Exception as e:
            logger.error(f"Failed to get tool instances data: {e}")
            raise

    def _convert_workflow_to_dto(self, workflow_data: dict[str, Any]) -> WorkflowDto:
        """Convert workflow data to DTO.

        Args:
            workflow_data: Workflow data dictionary

        Returns:
            WorkflowDto object
        """
        return WorkflowDto(
            id=workflow_data.get("id"),
        )

    def _convert_tool_instances_to_dtos(
        self, tool_instances_data: list[dict[str, Any]]
    ) -> list[ToolInstanceDto]:
        """Convert tool instances data to DTOs.

        Args:
            tool_instances_data: List of tool instance data dictionaries

        Returns:
            List of ToolInstanceDto objects
        """
        dtos = []
        for tool_data in tool_instances_data:
            dto = ToolInstanceDto(
                id=tool_data.get("id"),
                tool_id=tool_data.get("tool_id"),
                step=tool_data.get("step", 1),
                workflow=self.workflow_id,
                metadata=tool_data.get("metadata", {}),
                properties=tool_data.get("properties"),
                image_name=tool_data.get("image_name"),
                image_tag=tool_data.get("image_tag"),
            )
            dtos.append(dto)

        return dtos

    def create_workflow_execution(
        self,
        total_files: int = 0,
        tags: list[str] | None = None,
    ) -> str:
        """Create workflow execution via backend API.

        Args:
            total_files: Total number of files to process
            tags: Optional list of tags

        Returns:
            Execution ID
        """
        try:
            execution_data = {
                "workflow_id": self.workflow_id,
                "pipeline_id": self.pipeline_id,
                "single_step": self.single_step,
                "scheduled": self.scheduled,
                "execution_id": self.execution_id,
                "mode": self.mode,
                "total_files": total_files,
                "tags": tags or [],
                "organization_id": self.organization_id,
            }

            response = self.api_client.create_workflow_execution(execution_data)
            execution_id = response.get("execution_id")

            if not execution_id:
                raise Exception("No execution ID returned from API")

            self.execution_id = execution_id
            logger.info(f"Created workflow execution: {execution_id}")

            return execution_id

        except Exception as e:
            logger.error(f"Failed to create workflow execution: {e}")
            raise

    def update_execution_status(
        self,
        status: ExecutionStatus,
        error: str | None = None,
        increment_attempt: bool = False,
        total_files: int | None = None,
        completed_files: int | None = None,
        failed_files: int | None = None,
    ) -> None:
        """Update execution status via backend API.

        Args:
            status: New execution status
            error: Optional error message
            increment_attempt: Whether to increment attempt count
            total_files: Optional total files count
            completed_files: Optional completed files count
            failed_files: Optional failed files count
        """
        try:
            # Use individual parameters as expected by the API client method
            self.api_client.update_workflow_execution_status(
                execution_id=self.execution_id,
                status=status,
                error_message=error,
                total_files=total_files,
                organization_id=self.organization_id,
            )
            logger.info(f"Updated execution {self.execution_id} status to {status}")

        except Exception as e:
            logger.error(f"Failed to update execution status: {e}")
            raise

    def compile_workflow(self) -> bool:
        """Compile workflow configuration.

        This matches the backend compilation logic but uses API calls
        instead of direct tool registry access.

        Returns:
            True if compilation successful
        """
        try:
            response = self.api_client.compile_workflow(
                workflow_id=self.workflow_id,
                execution_id=self.execution_id,
                organization_id=self.organization_id,
            )

            compilation_successful = response.get("success", False)

            if compilation_successful:
                logger.info(f"Workflow {self.workflow_id} compiled successfully")
            else:
                error = response.get("error", "Unknown compilation error")
                logger.error(f"Workflow {self.workflow_id} compilation failed: {error}")

            return compilation_successful

        except Exception as e:
            logger.error(f"Failed to compile workflow: {e}")
            return False

    def execute_workflow_with_files(
        self, source_files: dict[str, FileHash]
    ) -> dict[str, Any]:
        """Execute workflow with provided source files.

        This is the main entry point for workflow execution, matching
        the backend execution patterns.

        Args:
            source_files: Dictionary of source files to process

        Returns:
            Execution result dictionary
        """
        try:
            logger.info(f"Starting workflow execution with {len(source_files)} files")

            # Update execution status to executing
            self.update_execution_status(
                status=ExecutionStatus.EXECUTING,
                total_files=len(source_files),
            )

            # Create file batches for processing
            file_batches = self._create_file_batches(source_files)

            # Submit batches for processing
            batch_results = self._execute_file_batches(file_batches)

            # Aggregate results
            execution_result = self._aggregate_batch_results(batch_results)

            # Update final execution status
            final_status = (
                ExecutionStatus.COMPLETED
                if execution_result.get("success", False)
                else ExecutionStatus.ERROR
            )

            self.update_execution_status(
                status=final_status,
                completed_files=execution_result.get("completed_files", 0),
                failed_files=execution_result.get("failed_files", 0),
                error=execution_result.get("error"),
            )

            logger.info(f"Workflow execution completed with status: {final_status}")
            return execution_result

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            self.update_execution_status(
                status=ExecutionStatus.ERROR,
                error=str(e),
            )
            raise

    def _create_file_batches(
        self, source_files: dict[str, FileHash]
    ) -> list[dict[str, Any]]:
        """Create file batches for processing.

        Args:
            source_files: Source files to batch

        Returns:
            List of file batch data structured for FileBatchData
        """
        # Convert FileHash objects to batch format
        files_list = []
        for file_path, file_hash in source_files.items():
            files_list.append(
                {
                    "file_name": file_hash.file_name,
                    "file_path": file_hash.file_path,
                    "file_hash": file_hash.file_hash,
                    "file_size": file_hash.file_size,
                    "mime_type": file_hash.mime_type,
                    "provider_file_uuid": file_hash.provider_file_uuid,
                    "source_connection_type": file_hash.source_connection_type,
                    "fs_metadata": file_hash.fs_metadata,
                }
            )

        # Create batch data with correct FileBatchData structure
        # The file processing worker expects 'files' (list) and 'file_data' (WorkerFileData)
        batch_data = {
            "files": files_list,
            "file_data": {
                "workflow_id": self.workflow_id,
                "execution_id": self.execution_id,
                "organization_id": self.organization_id,
                "pipeline_id": self.pipeline_id,
                "single_step": self.single_step,
                "use_file_history": self.use_file_history,
                "scheduled": self.scheduled,
                "mode": self.mode,
                "q_file_no_list": [],  # Empty for now, can be populated if needed
            },
        }

        return [batch_data]

    def _execute_file_batches(
        self, file_batches: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Execute file batches using workers.

        Args:
            file_batches: List of file batch data

        Returns:
            List of batch execution results
        """
        batch_results = []

        for batch_data in file_batches:
            try:
                # Submit batch to file processing worker
                result = self.api_client.submit_file_batch_for_processing(batch_data)
                batch_results.append(result)

            except Exception as e:
                logger.error(f"Failed to execute file batch: {e}")
                batch_results.append(
                    {
                        "success": False,
                        "error": str(e),
                        "batch_id": batch_data.get("batch_id"),
                    }
                )

        return batch_results

    def _aggregate_batch_results(
        self, batch_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Aggregate results from file batch processing.

        Args:
            batch_results: List of batch processing results

        Returns:
            Aggregated execution result
        """
        total_batches = len(batch_results)
        successful_batches = sum(
            1 for result in batch_results if result.get("success", False)
        )
        failed_batches = total_batches - successful_batches

        completed_files = sum(
            result.get("completed_files", 0) for result in batch_results
        )
        failed_files = sum(result.get("failed_files", 0) for result in batch_results)

        errors = [result.get("error") for result in batch_results if result.get("error")]

        return {
            "success": failed_batches == 0,
            "total_batches": total_batches,
            "successful_batches": successful_batches,
            "failed_batches": failed_batches,
            "completed_files": completed_files,
            "failed_files": failed_files,
            "error": "; ".join(errors) if errors else None,
        }
