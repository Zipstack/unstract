import logging
from typing import Any
from uuid import UUID

from plugins.workflow_manager.workflow_v2.utils import WorkflowUtil
from tool_instance_v2.constants import ToolInstanceKey
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from utils.constants import Account
from utils.local_context import StateStore

from backend.workers.file_processing.file_processing import app as file_processing_app
from unstract.workflow_execution.enums import LogComponent, LogLevel, LogStage, LogState
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
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.dto import ChunkData, FileData
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.exceptions import (
    WorkflowDoesNotExistError,
    WorkflowExecutionError,
)
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class FileExecutionTasks:
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
    def process_file_chunk(self, chunk_data) -> dict[str, Any]:
        """Process a chunk of files in parallel using Celery.

        Args:
            chunk_data (dict): Contains all necessary data to process files in the chunk
                - files: List of (file_name, file_hash) tuples
                - workflow_id: ID of the workflow
                - source_config: Source connector configuration
                - destination_config: Destination connector configuration
                - execution_id: ID of execution service
                - single_step: Whether to process in single step mode
        """
        chunk_data = ChunkData.from_dict(chunk_data)
        file_data = chunk_data.file_data
        logger.info(f"File processing context {file_data}")

        organization_id = file_data.organization_id
        StateStore.set(Account.ORGANIZATION_ID, organization_id)

        # Use proper logger instead of print
        logger.info(
            f"Starting to process file chunk for execution {file_data.execution_id}"
        )
        logger.debug(f"Chunk data received: {chunk_data}")

        successful_files = 0
        failed_files = 0
        execution_id = file_data.execution_id
        workflow_id = file_data.workflow_id
        # Reconstruct necessary objects
        workflow = FileExecutionTasks.get_workflow_by_id(str(workflow_id))
        workflow_execution = WorkflowExecution.objects.get(id=UUID(execution_id))

        total_files = len(chunk_data.files)
        q_file_no_list = (
            WorkflowUtil.get_q_no_list(workflow, total_files) if total_files > 0 else []
        )

        logger.info(
            f"Processing {total_files} files of execution {execution_id} in a chunk"
        )

        for file_number, (file_name, file_hash_dict) in enumerate(chunk_data.files, 1):
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
            )
            file_hash = WorkflowUtil.add_file_destination_filehash(
                file_number,
                q_file_no_list,
                file_hash,
            )
            file_execution_result = FileExecutionTasks._process_file(
                current_file_idx=file_number,
                total_files=total_files,
                file_data=file_data,
                file_hash=file_hash,
                workflow_execution=workflow_execution,
            )
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
        queue="file_processing",
        max_retries=0,  # Maximum number of retries
        retry_backoff=True,
        retry_backoff_max=500,  # Max delay between retries (500 seconds)
        retry_jitter=True,  # Add random jitter to prevent thundering herd
        default_retry_delay=5,  # Initial retry delay (5 seconds)
    )
    def process_chunk_callback(self, results, **kwargs):
        """Callback task to handle chunk processing results.

        Args:
            results (list): List of results from each chunk
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
            source_config (SourceConfig): Source configuration
            destination_config (DestinationConfig): Destination configuration
            single_step (bool): Whether to execute in single step mode
            file_hash (FileHash): File hash
            organization_id (str): Organization ID
            workflow_execution (WorkflowExecution): Workflow execution instance
            use_file_history (bool): Whether to use file history
            scheduled (bool): Whether the execution is scheduled
            execution_mode (tuple[str, str]): Execution mode

        Returns:
            FileExecutionResult: Result of the file execution
        """
        organization_id = file_data.organization_id
        pipeline_id = file_data.pipeline_id
        single_step = file_data.single_step
        scheduled = file_data.scheduled
        execution_mode = file_data.execution_mode
        use_file_history = file_data.use_file_history
        source_config = SourceConfig.from_json(file_data.source_config)
        destination_config = DestinationConfig.from_json(file_data.destination_config)

        workflow: Workflow = workflow_execution.workflow
        pipeline_id: str = str(workflow_execution.pipeline_id)
        endpoint: WorkflowEndpoint = WorkflowEndpoint.objects.get(
            workflow=workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
        )

        is_api = endpoint.connection_type == WorkflowEndpoint.ConnectionType.API
        execution_id = str(workflow_execution.id)
        input_file = file_hash.file_path

        workflow_file_execution: WorkflowFileExecution = (
            WorkflowFileExecution.objects.get_or_create_file_execution(
                workflow_execution=workflow_execution,
                file_hash=file_hash,
                is_api=is_api,
            )
        )

        workflow_log = WorkflowLog(
            execution_id=execution_id,
            log_stage=LogStage.PROCESSING,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            file_execution_id=str(workflow_file_execution.id),
        )
        source_config.file_execution_id = str(workflow_file_execution.id)
        destination_config.file_execution_id = str(workflow_file_execution.id)

        source = SourceConnector.from_config(workflow_log, source_config)
        destination = DestinationConnector.from_config(workflow_log, destination_config)
        workflow_file_execution.update_status(status=ExecutionStatus.EXECUTING)
        file_execution_id = str(workflow_file_execution.id)
        file_name = file_hash.file_name
        destination.delete_file_execution_directory()

        # This will add the file to the volume
        file_content_hash = source.add_file_to_volume(
            workflow_file_execution=workflow_file_execution,
            tags=workflow_execution.tag_names,
            file_hash=file_hash,
        )

        # Update file_hash after adding to volume
        file_hash.file_hash = file_content_hash
        workflow_file_execution.update(file_hash=file_content_hash)
        file_history = FileHistoryHelper.get_file_history(
            workflow=workflow, cache_key=file_content_hash
        )

        tool_execution_result: str | None = None
        execution_metadata: dict[str, Any] | None = None
        error_message: str | None = None

        # Ensure no duplicate file processing
        if file_history and not destination.is_api:
            logger.info(f"Skipping '{file_name}', already processed.")
            workflow_log.publish_log(
                f"Skipping '{file_name}', already processed.", LogLevel.INFO
            )
            return file_execution_id, None

        try:
            tool_instances: list[ToolInstance] = (
                ToolInstanceHelper.get_tool_instances_by_workflow(
                    workflow.id, ToolInstanceKey.STEP
                )
            )
            execution_service = FileExecutionTasks._build_workflow_execution_service(
                organization_id=organization_id,
                workflow=workflow,
                tool_instances=tool_instances,
                pipeline_id=pipeline_id,
                single_step=single_step,
                scheduled=scheduled,
                execution_mode=execution_mode,
                workflow_execution=workflow_execution,
                use_file_history=use_file_history,
                file_execution_id=file_execution_id,
            )
            execution_service.initiate_tool_execution(
                current_file_idx, total_files, file_name, single_step
            )
            workflow_file_execution.update_status(status=ExecutionStatus.EXECUTING)
            if not file_hash.is_executed:
                execution_service.execute_input_file(
                    file_execution_id=file_execution_id,
                    file_name=file_name,
                    single_step=single_step,
                    workflow_file_execution=workflow_file_execution,
                )
        except StopExecution:
            workflow_file_execution.update_status(status=ExecutionStatus.STOPPED)
            raise
        except WorkflowExecutionError as e:
            error_message = f"Error processing file '{file_name}': {e}"
            workflow_log.publish_log(error_message, level=LogLevel.ERROR)
            logger.error(error_message)
            error = error_message
        except Exception as e:
            error_message = f"Unexpected error processing file '{file_name}': {str(e)}"
            logger.error(error_message, stack_info=True, exc_info=True)
            workflow_log.publish_log(error_message, level=LogLevel.ERROR)
            error = error_message
            # Handling error based on destination and continuing for other files
        else:
            error = None
        workflow_log.publish_update_log(
            LogState.RUNNING,
            f"Processing output for {file_name}",
            LogComponent.DESTINATION,
        )
        try:
            if not error:
                tool_execution_result = destination.handle_output(
                    file_name=file_name,
                    file_hash=file_hash,
                    workflow=workflow,
                    input_file_path=input_file,
                    file_execution_id=file_execution_id,
                )
            if file_history and destination.is_api:
                execution_metadata = destination.get_metadata(file_history)
        except Exception as e:
            error_message = f"Error during output processing for '{file_name}': {str(e)}"
            logger.error(error_message, stack_info=True, exc_info=True)
            workflow_log.publish_log(error_message, level=LogLevel.ERROR)
            error = error_message
        finally:
            execution_service.log_total_cost_per_file(
                run_id=file_execution_id, file_name=file_name
            )
            workflow_log.publish_update_log(
                LogState.SUCCESS,
                f"{file_name}'s output is processed successfully",
                LogComponent.DESTINATION,
            )
            workflow_file_execution.update_status(
                status=ExecutionStatus.ERROR if error else ExecutionStatus.COMPLETED,
                execution_error=error if error else None,
            )
            file_execution_result = FileExecutionResult(
                file=file_hash.file_name,
                file_execution_id=file_execution_id,
                error=error_message,
                result=tool_execution_result,
                metadata=execution_metadata,
            )
            ResultCacheUtils.update_api_results(
                workflow_id=workflow.id,
                execution_id=execution_id,
                api_result=file_execution_result,
            )
        return file_execution_result
