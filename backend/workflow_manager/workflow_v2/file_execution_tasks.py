import logging
from typing import Any
from uuid import UUID

from account_v2.constants import Common
from plugins.workflow_manager.workflow_v2.utils import WorkflowUtil
from tool_instance_v2.constants import ToolInstanceKey
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from utils.constants import Account
from utils.local_context import StateStore

from backend.workers.file_processing.constants import QueueNames
from backend.workers.file_processing.file_processing import app as file_processing_app
from unstract.workflow_execution.enums import LogComponent, LogStage, LogState
from unstract.workflow_execution.exceptions import StopExecution
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.dto import (
    DestinationConfig,
    FileExecutionResult,
    FileHash,
    SourceConfig,
)
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.result_cache_utils import ResultCacheUtils
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.utils.pipeline_utils import PipelineUtils
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.dto import (
    ExecutionContext,
    FileBatchData,
    FileData,
    FinalOutputResult,
    ToolExecutionResult,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.exceptions import (
    WorkflowDoesNotExistError,
    WorkflowExecutionError,
)
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.file_history import FileHistory
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class FileExecutionTasks:
    @staticmethod
    def get_queue_name(source: SourceConnector) -> str:
        is_api = source.endpoint.connection_type == WorkflowEndpoint.ConnectionType.API
        return QueueNames.API_FILE_PROCESSING if is_api else QueueNames.FILE_PROCESSING

    @staticmethod
    def get_workflow_by_id(id: str) -> Workflow:
        try:
            workflow: Workflow = Workflow.objects.get(pk=id)
            return workflow
        except Workflow.DoesNotExist:
            logger.error(f"Error getting workflow: {id}")
            raise WorkflowDoesNotExistError()

    @staticmethod
    def _build_workflow_execution_service(
        organization_id: str | None,
        workflow: Workflow,
        tool_instances: list[ToolInstance],
        pipeline_id: str | None,
        single_step: bool,
        scheduled: bool,
        execution_mode: tuple[str, str],
        workflow_execution: WorkflowExecution,
        use_file_history: bool = True,  # Will be False for API deployment alone
        file_execution_id: str | None = None,
    ) -> WorkflowExecutionServiceHelper:
        workflow_execution_service = WorkflowExecutionServiceHelper(
            organization_id=organization_id,
            workflow=workflow,
            tool_instances=tool_instances,
            pipeline_id=pipeline_id,
            single_step=single_step,
            scheduled=scheduled,
            mode=execution_mode,
            workflow_execution=workflow_execution,
            use_file_history=use_file_history,
            file_execution_id=file_execution_id,
        )
        workflow_execution_service.build()
        return workflow_execution_service

    @file_processing_app.task(
        bind=True,
        max_retries=0,  # Maximum number of retries
        ignore_result=False,  # result is passed to the callback task
        retry_backoff=True,
        retry_backoff_max=500,  # Max delay between retries (500 seconds)
        retry_jitter=True,  # Add random jitter to prevent thundering herd
        default_retry_delay=5,  # Initial retry delay (5 seconds)
    )
    def process_file_batch(self, file_batch_data) -> dict[str, Any]:
        """Process a batch of files in parallel using Celery.

        Args:
            file_batch_data (dict): Contains all necessary data to process files in the batch
                - files: List of (file_name, file_hash) tuples
                - workflow_id: ID of the workflow
                - source_config: Source connector configuration
                - destination_config: Destination connector configuration
                - execution_id: ID of execution service
                - single_step: Whether to process in single step mode
        """
        file_batch_data = FileBatchData.from_dict(file_batch_data)
        file_data = file_batch_data.file_data
        logger.info(f"File processing context {file_data}")

        organization_id = file_data.organization_id
        StateStore.set(Account.ORGANIZATION_ID, organization_id)

        # Use proper logger instead of print
        logger.info(
            f"Starting to process file batch for execution {file_data.execution_id}"
        )
        logger.debug(f"Batch data received: {file_batch_data}")

        successful_files = 0
        failed_files = 0
        execution_id = file_data.execution_id
        workflow_id = file_data.workflow_id
        # Reconstruct necessary objects
        workflow = FileExecutionTasks.get_workflow_by_id(str(workflow_id))
        workflow_execution: WorkflowExecution = WorkflowExecution.objects.get(
            id=UUID(execution_id)
        )
        log_events_id = workflow_execution.execution_log_id
        StateStore.set(Common.LOG_EVENTS_ID, log_events_id)

        total_files = len(file_batch_data.files)
        q_file_no_list = set(file_data.q_file_no_list)

        logger.info(
            f"Processing {total_files} files of execution {execution_id} in a batch"
        )

        for file_number, (file_name, file_hash_dict) in enumerate(
            file_batch_data.files, 1
        ):
            file_hash = FileHash(
                file_path=file_hash_dict.get("file_path"),
                file_name=file_hash_dict.get("file_name"),
                source_connection_type=file_hash_dict.get("source_connection_type"),
                file_hash=file_hash_dict.get("file_hash"),
                file_size=file_hash_dict.get("file_size"),
                provider_file_uuid=file_hash_dict.get("provider_file_uuid"),
                mime_type=file_hash_dict.get("mime_type"),
                fs_metadata=file_hash_dict.get("fs_metadata"),
                file_destination=file_hash_dict.get("file_destination"),
                is_executed=file_hash_dict.get("is_executed"),
                file_number=file_hash_dict.get("file_number"),
            )
            file_hash = WorkflowUtil.add_file_destination_filehash(
                file_hash.file_number,
                q_file_no_list,
                file_hash,
            )
            try:
                file_execution_result = FileExecutionTasks._process_file(
                    current_file_idx=file_number,
                    total_files=total_files,
                    file_data=file_data,
                    file_hash=file_hash,
                    workflow_execution=workflow_execution,
                )
            except Exception as e:
                # It is unlikely to happen but if it does, we should handle it
                # TODO: Add proper error handling and return error message
                logger.error(
                    f"Error processing file {file_name}: {str(e)}", exc_info=True
                )
                failed_files += 1
                ExecutionCacheUtils.increment_failed_files(
                    workflow_id=workflow.id,
                    execution_id=execution_id,
                )
                continue

            if file_execution_result.error:
                failed_files += 1
                ExecutionCacheUtils.increment_failed_files(
                    workflow_id=workflow.id,
                    execution_id=execution_id,
                )
            else:
                successful_files += 1
                ExecutionCacheUtils.increment_completed_files(
                    workflow_id=workflow.id,
                    execution_id=execution_id,
                )
        return {
            "successful_files": successful_files,
            "failed_files": failed_files,
        }

    @file_processing_app.task(
        bind=True,
        max_retries=0,  # Maximum number of retries
        retry_backoff=True,
        retry_backoff_max=500,  # Max delay between retries (500 seconds)
        retry_jitter=True,  # Add random jitter to prevent thundering herd
        default_retry_delay=5,  # Initial retry delay (5 seconds)
    )
    def process_batch_callback(self, results, **kwargs):
        """Callback task to handle batch processing results.

        Args:
            results (list): List of results from each batch
                Each result is a dictionary containing:
                - successful_files: Number of successfully processed files
                - failed_files: Number of failed files
                - error_messages: List of error messages
                - execution_id: ID of the execution
        """
        execution_id = kwargs.get("execution_id")
        workflow_execution: WorkflowExecution = WorkflowExecution.objects.get(
            id=execution_id
        )
        workflow = workflow_execution.workflow
        organization = workflow.organization
        organization_id = organization.organization_id
        pipeline_id = str(workflow_execution.pipeline_id)
        log_events_id = workflow_execution.execution_log_id
        workflow_log = WorkflowLog(
            execution_id=execution_id,
            log_stage=LogStage.FINALIZE,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
        )
        StateStore.set(Common.LOG_EVENTS_ID, log_events_id)

        # Set organization ID in StateStore
        StateStore.set(Account.ORGANIZATION_ID, organization_id)

        if not results:
            return None

        # Aggregate results
        total_successful = sum(result["successful_files"] for result in results)
        total_failed = sum(result["failed_files"] for result in results)

        total_files = total_successful + total_failed

        # Update final status
        final_status = (
            ExecutionStatus.COMPLETED if total_successful else ExecutionStatus.ERROR
        )
        error_message = None
        # Update execution service with final results
        workflow_execution.update_execution(
            status=final_status,
            error=error_message,
        )
        PipelineUtils.update_pipeline_status(
            pipeline_id=pipeline_id, workflow_execution=workflow_execution
        )
        # clean up execution and api storage directories
        DestinationConnector.delete_execution_and_api_storage_dir(
            workflow_id=workflow.id, execution_id=execution_id
        )
        workflow_log.publish_average_cost_log(
            logger=logger,
            total_files=total_files,
            execution_id=execution_id,
            total_cost=workflow_execution.aggregated_usage_cost,
        )
        workflow_log.publish_final_workflow_logs(
            total_files=total_files,
            successful_files=total_successful,
            failed_files=total_failed,
        )
        return {
            "execution_id": execution_id,
            "total_files": total_files,
            "successful_files": total_successful,
            "failed_files": total_failed,
            "error_message": error_message,
            "status": final_status,
        }

    @classmethod
    def _process_file(
        cls,
        current_file_idx: int,
        total_files: int,
        file_data: FileData,
        file_hash: FileHash,
        workflow_execution: WorkflowExecution,
    ) -> FileExecutionResult:
        """Process a single file in the workflow.

        Args:
            current_file_idx (int): Index of the current file
            total_files (int): Total number of files
            file_data (FileData): File data
            file_hash (FileHash): File hash
            workflow_execution (WorkflowExecution): Workflow execution instance

        Returns:
            FileExecutionResult: Result of the file execution
        """
        try:
            # Initialization Phase
            execution_context = cls._initialize_execution_context(
                file_data, file_hash, workflow_execution
            )
            workflow_log = execution_context.workflow_log
            workflow_file_execution = execution_context.workflow_file_execution
            source_config = execution_context.source_config
            destination_config = execution_context.destination_config
            source = SourceConnector.from_config(workflow_log, source_config)
            destination = DestinationConnector.from_config(
                workflow_log, destination_config
            )
            destination.delete_file_execution_directory()

            # File Preparation Phase
            content_hash = cls._prepare_file_for_processing(
                source,
                workflow_log,
                workflow_file_execution,
                file_hash,
                workflow_execution,
            )

            # History Check Phase
            if early_result := cls._check_processing_history(
                destination,
                workflow_execution.workflow,
                content_hash,
                file_hash,
                workflow_log,
                workflow_file_execution,
            ):
                cls._complete_execution(
                    workflow_file_execution=workflow_file_execution,
                    workflow_log=workflow_log,
                    error=early_result.error,
                )
                return early_result

            # Core Execution Phase
            execution_result = cls._execute_workflow_steps(
                file_data,
                workflow_execution,
                workflow_file_execution,
                file_hash,
                current_file_idx,
                total_files,
            )

            # Finalization Phase
            return cls._finalize_execution(
                workflow_execution,
                workflow_file_execution,
                file_hash,
                workflow_log,
                destination,
                execution_result,
            )
        except Exception as error:
            error_msg = f"File execution failed: {error}"
            workflow_log.log_error(logger=logger, message=error_msg)
            workflow_file_execution.update_status(
                status=ExecutionStatus.ERROR, execution_error=error_msg[:500]
            )
            result = FinalOutputResult(output=None, metadata=None, error=error_msg)
            return cls._build_final_result(
                workflow_execution=workflow_execution,
                workflow_file_execution=workflow_file_execution,
                file_hash=file_hash,
                is_api=destination.is_api,
                result=result,
                error=error_msg,
            )

    @classmethod
    def _initialize_execution_context(
        cls,
        file_data: FileData,
        file_hash: FileHash,
        workflow_execution: WorkflowExecution,
    ) -> ExecutionContext:
        """Set up all required execution context objects and configurations."""
        workflow = workflow_execution.workflow
        endpoint: WorkflowEndpoint = WorkflowEndpoint.objects.get(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
        )

        is_api = endpoint.connection_type == WorkflowEndpoint.ConnectionType.API

        # Create execution record
        file_execution: WorkflowFileExecution = (
            WorkflowFileExecution.objects.get_or_create_file_execution(
                workflow_execution=workflow_execution,
                file_hash=file_hash,
                is_api=is_api,
            )
        )

        # Create configurations
        source_config = SourceConfig.from_json(file_data.source_config)
        destination_config = DestinationConfig.from_json(file_data.destination_config)
        source_config.file_execution_id = destination_config.file_execution_id = str(
            file_execution.id
        )

        # Initialize logging
        workflow_log = WorkflowLog(
            execution_id=str(workflow_execution.id),
            log_stage=LogStage.PROCESSING,
            organization_id=file_data.organization_id,
            pipeline_id=str(workflow_execution.pipeline_id),
            file_execution_id=str(file_execution.id),
        )

        return ExecutionContext(
            workflow_log=workflow_log,
            workflow_file_execution=file_execution,
            source_config=source_config,
            destination_config=destination_config,
        )

    @classmethod
    def _prepare_file_for_processing(
        cls,
        source: SourceConnector,
        workflow_log: WorkflowLog,
        workflow_file_exec: WorkflowFileExecution,
        file_hash: FileHash,
        workflow_execution: WorkflowExecution,
    ) -> str:
        """Handle file preparation and volume storage."""
        workflow_file_exec.update_status(ExecutionStatus.EXECUTING)

        try:
            content_hash = source.add_file_to_volume(
                workflow_file_execution=workflow_file_exec,
                tags=workflow_execution.tag_names,
                file_hash=file_hash,
            )
            file_hash.file_hash = content_hash
            workflow_file_exec.update(file_hash=content_hash)
            return content_hash
        except FileNotFoundError as error:
            error_msg = f"File not Found in execution dir: {error}"
            workflow_log.log_error(logger=logger, message=error_msg)
            raise WorkflowExecutionError(error_msg) from error
        except Exception as error:
            error_msg = f"File preparation failed: {error}"
            workflow_log.log_error(logger=logger, message=error_msg)
            raise WorkflowExecutionError(error_msg) from error

    @classmethod
    def _check_processing_history(
        cls,
        destination: DestinationConnector,
        workflow: Workflow,
        content_hash: str,
        file_hash: FileHash,
        workflow_log: WorkflowLog,
        workflow_file_exec: WorkflowFileExecution,
    ) -> FileExecutionResult | None:
        """Check for existing file processing history and return early result if found."""
        if destination.is_api:
            return None

        file_history = FileHistoryHelper.get_file_history(
            workflow=workflow, cache_key=content_hash
        )
        if not file_history:
            return None

        workflow_log.log_info(f"Skipping duplicate '{file_hash.file_name}'")
        return FileExecutionResult(
            file=file_hash.file_name,
            file_execution_id=str(workflow_file_exec.id),
            error=None,
            result=file_history.result,
            metadata=file_history.metadata,
        )

    @classmethod
    def _execute_workflow_steps(
        cls,
        file_data: FileData,
        workflow_execution: WorkflowExecution,
        workflow_file_execution: WorkflowFileExecution,
        file_hash: FileHash,
        current_file_idx: int,
        total_files: int,
    ) -> ToolExecutionResult:
        """Execute main workflow processing steps with proper error handling."""
        tool_instances: list[ToolInstance] = (
            ToolInstanceHelper.get_tool_instances_by_workflow(
                file_data.workflow_id, ToolInstanceKey.STEP
            )
        )
        execution_service = cls._build_workflow_execution_service(
            organization_id=file_data.organization_id,
            workflow=workflow_execution.workflow,
            tool_instances=tool_instances,
            pipeline_id=file_data.pipeline_id,
            single_step=file_data.single_step,
            scheduled=file_data.scheduled,
            execution_mode=file_data.execution_mode,
            workflow_execution=workflow_execution,
            use_file_history=file_data.use_file_history,
            file_execution_id=str(workflow_file_execution.id),
        )

        try:
            execution_service.initiate_tool_execution(
                current_file_idx=current_file_idx,
                total_files=total_files,
                file_name=file_hash.file_name,
                single_step=file_data.single_step,
            )

            if not file_hash.is_executed:
                execution_service.execute_input_file(
                    file_execution_id=str(workflow_file_execution.id),
                    file_name=file_hash.file_name,
                    single_step=file_data.single_step,
                    workflow_file_execution=workflow_file_execution,
                )
                # Log execution costs
                execution_service.log_total_cost_per_file(
                    run_id=str(workflow_file_execution.id), file_name=file_hash.file_name
                )
            tool_execution_result = ToolExecutionResult(error=None, result=None)
            return tool_execution_result
        except StopExecution:
            workflow_file_execution.update_status(status=ExecutionStatus.STOPPED)
            raise
        except WorkflowExecutionError as error:
            tool_execution_result = ToolExecutionResult(
                error=str(error),
                result=None,
            )
            logger.error(f"Workflow execution failed: {str(error)}", exc_info=True)
            return tool_execution_result
        except Exception as error:
            tool_execution_result = ToolExecutionResult(
                error=f"Unexpected error: {error}",
                result=None,
            )
            logger.error(f"Workflow execution failed: {str(error)}", exc_info=True)
            return tool_execution_result

    @classmethod
    def _finalize_execution(
        cls,
        workflow_execution: WorkflowExecution,
        workflow_file_execution: WorkflowFileExecution,
        file_hash: FileHash,
        workflow_log: WorkflowLog,
        destination: DestinationConnector,
        execution_result: ToolExecutionResult,
    ) -> FileExecutionResult:
        """Handle final processing steps and result generation."""
        result = cls._process_final_output(
            destination,
            workflow_execution.workflow,
            file_hash,
            str(workflow_file_execution.id),
            execution_result.error,
        )

        cls._complete_execution(
            workflow_file_execution=workflow_file_execution,
            workflow_log=workflow_log,
            error=result.error or execution_result.error,
        )

        return cls._build_final_result(
            workflow_execution=workflow_execution,
            workflow_file_execution=workflow_file_execution,
            file_hash=file_hash,
            is_api=destination.is_api,
            result=result,
            error=result.error or execution_result.error,
        )

    @classmethod
    def _process_final_output(
        cls,
        destination: DestinationConnector,
        workflow: Workflow,
        file_hash: FileHash,
        file_execution_id: str,
        processing_error: str | None,
    ) -> FinalOutputResult:
        """Handle final output processing and metadata collection."""
        output_result = None
        execution_metadata = None

        try:
            if destination.use_file_history:
                # Collect metadata from file history if available
                file_history = FileHistoryHelper.get_file_history(
                    workflow=workflow, cache_key=file_hash.file_hash
                )
            else:
                file_history = None

            if not processing_error:
                # Process final output through destination
                output_result = destination.handle_output(
                    file_name=file_hash.file_name,
                    file_hash=file_hash,
                    file_history=file_history,
                    workflow=workflow,
                    input_file_path=file_hash.file_path,
                    file_execution_id=file_execution_id,
                )

            if destination.is_api:
                execution_metadata = destination.get_metadata(file_history)
            if cls._should_create_file_history(destination, file_history, output_result):
                FileHistoryHelper.create_file_history(
                    file_hash=file_hash,
                    workflow=workflow,
                    status=ExecutionStatus.COMPLETED,
                    result=output_result,
                    metadata=execution_metadata,
                    file_name=file_hash.file_name,
                )
        except Exception as e:
            error_msg = f"Final output processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return FinalOutputResult(output=None, metadata=None, error=error_msg)

        return FinalOutputResult(
            output=output_result, metadata=execution_metadata, error=None
        )

    @classmethod
    def _should_create_file_history(
        cls,
        destination: DestinationConnector,
        file_history: FileHistory | None,
        output_result: str | None,
    ) -> bool:
        """Determine whether a new FileHistory record should be created.

        Returns True if:
        - File history is enabled for the destination,
        - No existing file history record is present, and
        - Either:
            - The destination is not API, or
            - The destination is API and a valid output_result exists.

        Args:
            destination: Destination connector
            file_history: File history
            output_result: Output result

        Returns:
            bool: True if file history should be created, False otherwise
        """
        if not destination.use_file_history or file_history:
            return False
        if destination.is_api and not output_result:
            return False
        return True

    @classmethod
    def _complete_execution(
        cls,
        workflow_file_execution: WorkflowFileExecution,
        workflow_log: WorkflowLog,
        error: str | None,
    ) -> None:
        """Final status updates for the file execution."""
        try:
            # Update execution status
            final_status = ExecutionStatus.ERROR if error else ExecutionStatus.COMPLETED
            workflow_file_execution.update_status(
                status=final_status, execution_error=error
            )

            # Publish final log status
            log_state = LogState.ERROR if error else LogState.SUCCESS
            workflow_log.publish_update_log(
                state=log_state,
                message=f"Execution {'failed' if error else 'completed'} for {workflow_file_execution.file_name}",
                component=LogComponent.DESTINATION,
            )

        except Exception as e:
            logger.error(f"Completion status update failed: {str(e)}", exc_info=True)

    @classmethod
    def _build_final_result(
        cls,
        workflow_execution: WorkflowExecution,
        workflow_file_execution: WorkflowFileExecution,
        file_hash: FileHash,
        is_api: bool,
        result: FinalOutputResult,
        error: str | None,
    ) -> FileExecutionResult:
        """Construct and cache the final execution result."""
        final_result = FileExecutionResult(
            file=file_hash.file_name,
            file_execution_id=str(workflow_file_execution.id),
            error=error,
            result=result.output,
            metadata=result.metadata,
        )

        if is_api:
            # Update cache with final result
            ResultCacheUtils.update_api_results(
                workflow_id=workflow_execution.workflow.id,
                execution_id=str(workflow_execution.id),
                api_result=final_result,
            )

        return final_result
