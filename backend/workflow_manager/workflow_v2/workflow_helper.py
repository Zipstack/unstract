import json
import logging
import math
import os
import time
import traceback
from typing import Any

from account_v2.constants import Common
from api_v2.models import APIDeployment
from api_v2.utils import APIDeploymentUtils
from celery import chord, current_task
from celery import exceptions as celery_exceptions
from celery.result import AsyncResult
from django.conf import settings
from django.db import IntegrityError
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers
from tool_instance_v2.constants import ToolInstanceKey
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from utils.cache_service import CacheService
from utils.constants import Account
from utils.local_context import StateStore
from utils.user_context import UserContext

from backend.celery_service import app as celery_app
from unstract.workflow_execution.enums import LogStage
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.dto import (
    FileHash,
)
from workflow_manager.endpoint_v2.result_cache_utils import ResultCacheUtils
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.execution.dto import ExecutionCache
from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.utils.workflow_log import WorkflowLog
from workflow_manager.workflow_v2.constants import (
    WorkflowErrors,
    WorkflowExecutionKey,
    WorkflowMessages,
)
from workflow_manager.workflow_v2.dto import (
    ExecutionResponse,
    FileBatchData,
    FileData,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus, SchemaEntity, SchemaType
from workflow_manager.workflow_v2.exceptions import (
    InvalidRequest,
    TaskDoesNotExistError,
    WorkflowDoesNotExistError,
    WorkflowExecutionError,
    WorkflowExecutionNotExist,
)
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.file_execution_tasks import FileExecutionTasks
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowHelper:
    @staticmethod
    def get_workflow_by_id(id: str) -> Workflow:
        try:
            workflow: Workflow = Workflow.objects.get(pk=id)
            return workflow
        except Workflow.DoesNotExist:
            logger.error(f"Error getting workflow: {id}")
            raise WorkflowDoesNotExistError()

    @staticmethod
    def get_active_workflow_by_project_id(project_id: str) -> Workflow:
        try:
            workflow: Workflow = Workflow.objects.filter(
                project_id=project_id, is_active=True
            ).first()
            if not workflow or workflow is None:
                raise WorkflowDoesNotExistError()
            return workflow
        except Workflow.DoesNotExist:
            raise WorkflowDoesNotExistError()

    @staticmethod
    def active_project_workflow(workflow_id: str) -> Workflow:
        workflow: Workflow = WorkflowHelper.get_workflow_by_id(workflow_id)
        workflow.is_active = True
        workflow.save()
        return workflow

    @classmethod
    def get_file_batches(
        cls, input_files: dict[str, FileHash]
    ) -> list[list[tuple[str, FileHash]]]:
        """_summary_

        Args:
            input_files (dict[str, FileHash]): input files

        Returns:
            batches: batches of input files
        """
        json_serializable_files = {
            file_name: file_hash.to_json() for file_name, file_hash in input_files.items()
        }

        # Prepare batches of files for parallel processing
        BATCH_SIZE = settings.MAX_PARALLEL_FILE_BATCHES  # Max number of batches
        file_items = list(json_serializable_files.items())

        # Calculate how many items per batch
        num_files = len(file_items)
        num_batches = min(BATCH_SIZE, num_files)
        items_per_batch = math.ceil(num_files / num_batches)

        # Split into batches
        batches = []
        for start_index in range(0, len(file_items), items_per_batch):
            end_index = start_index + items_per_batch
            batch = file_items[start_index:end_index]
            batches.append(batch)

        return batches

    @classmethod
    def process_input_files(
        cls,
        workflow: Workflow,
        source: SourceConnector,
        destination: DestinationConnector,
        workflow_log: WorkflowLog,
        workflow_execution: WorkflowExecution,
        single_step: bool,
        input_files: dict[str, FileHash],
        organization_id: str,
        pipeline_id: str,
        scheduled: bool,
        execution_mode: tuple[str, str],
        use_file_history: bool,
    ) -> str | None:
        total_files = len(input_files)
        workflow_log.publish_initial_workflow_logs(total_files=total_files)

        workflow_execution.update_execution(
            status=ExecutionStatus.EXECUTING, increment_attempt=True
        )

        if not input_files:
            logger.info(f"Execution {workflow_execution.id} no files to process")
            workflow_execution.update_execution(
                status=ExecutionStatus.COMPLETED,
            )
            return

        batches = cls.get_file_batches(input_files=input_files)
        batch_tasks = []
        mode = (
            execution_mode[1]
            if isinstance(execution_mode, tuple)
            else str(execution_mode)
        )
        result = None
        logger.info(
            f"Execution {workflow_execution.id} processing {total_files} files in {len(batches)} batches"
        )
        for batch in batches:
            # Convert all UUIDs to strings in batch_data
            file_data = FileData(
                workflow_id=str(workflow.id),
                source_config=source.get_config().to_json(),
                destination_config=destination.get_config().to_json(),
                execution_id=str(workflow_execution.id),
                single_step=single_step,
                organization_id=str(organization_id),
                pipeline_id=str(pipeline_id),
                scheduled=scheduled,
                execution_mode=mode,
                use_file_history=use_file_history,
            )
            batch_data = FileBatchData(files=batch, file_data=file_data)

            # Determine the appropriate queue based on execution_mode
            file_processing_queue = FileExecutionTasks.get_queue_name(source)

            # Send each batch to the dedicated file_processing queue
            batch_tasks.append(
                FileExecutionTasks.process_file_batch.s(batch_data.to_dict()).set(
                    queue=file_processing_queue
                )
            )
        try:
            result = chord(batch_tasks)(
                FileExecutionTasks.process_batch_callback.s(
                    execution_id=str(workflow_execution.id)
                ).set(queue=file_processing_queue)
            )
            if not result.id:
                exception = f"Failed to queue execution task {workflow_execution.id}"
                logger.error(exception)
                raise WorkflowExecutionError(exception)
            logger.info(f"Execution {workflow_execution.id} task queued successfully")
        except Exception as e:
            workflow_execution.update_execution(
                status=ExecutionStatus.ERROR,
                error=f"Error while processing files: {str(e)}",
            )
            return result.id

    @staticmethod
    def validate_tool_instances_meta(
        tool_instances: list[ToolInstance],
    ) -> None:
        for tool in tool_instances:
            ToolInstanceHelper.validate_tool_settings(
                user=tool.workflow.created_by,
                tool_uid=tool.tool_id,
                tool_meta=tool.metadata,
            )

    @staticmethod
    def run_workflow(
        workflow: Workflow,
        workflow_execution: WorkflowExecution,
        hash_values_of_files: dict[str, FileHash] = {},
        organization_id: str | None = None,
        pipeline_id: str | None = None,
        scheduled: bool = False,
        single_step: bool = False,
        execution_mode: tuple[str, str] | None = None,
        use_file_history: bool = True,
    ) -> ExecutionResponse:
        tool_instances: list[ToolInstance] = (
            ToolInstanceHelper.get_tool_instances_by_workflow(
                workflow.id, ToolInstanceKey.STEP
            )
        )
        WorkflowHelper.validate_tool_instances_meta(tool_instances=tool_instances)
        execution_mode = execution_mode or WorkflowExecution.Mode.INSTANT
        execution_id = str(workflow_execution.id)
        workflow_log = WorkflowLog(
            execution_id=workflow_execution.id,
            organization_id=organization_id,
            log_stage=LogStage.INITIALIZE,
            pipeline_id=pipeline_id,
        )
        source = SourceConnector(
            workflow=workflow,
            execution_id=execution_id,
            workflow_log=workflow_log,
            use_file_history=use_file_history,
            organization_id=organization_id,
        )
        destination = DestinationConnector(
            workflow=workflow,
            execution_id=execution_id,
            workflow_log=workflow_log,
            use_file_history=use_file_history,
        )
        try:
            # Validating endpoints
            source.validate()
            destination.validate()
            # Execution Process
            input_files, total_files = source.list_files_from_source(hash_values_of_files)
            workflow_execution.total_files = total_files
            workflow_execution.save()
            WorkflowHelper.process_input_files(
                workflow=workflow,
                source=source,
                destination=destination,
                workflow_log=workflow_log,
                workflow_execution=workflow_execution,
                single_step=single_step,
                input_files=input_files,
                organization_id=organization_id,
                pipeline_id=pipeline_id,
                scheduled=scheduled,
                use_file_history=use_file_history,
                execution_mode=execution_mode,
            )
            WorkflowHelper._update_pipeline_status(
                pipeline_id=pipeline_id, workflow_execution=workflow_execution
            )
            api_results = []
            return ExecutionResponse(
                str(workflow.id),
                str(workflow_execution.id),
                workflow_execution.status,
                log_id=workflow_log.messaging_channel,
                error=workflow_execution.error_message,
                mode=workflow_execution.execution_mode,
                result=api_results,
            )
        except Exception as e:
            logger.error(f"Error executing workflow {workflow}: {e}")
            logger.error(f"Error {traceback.format_exc()}")
            workflow_execution.update_execution(
                status=ExecutionStatus.ERROR,
                error=str(e),
            )
            WorkflowHelper._update_pipeline_status(
                pipeline_id=pipeline_id, workflow_execution=workflow_execution
            )
            raise

    @staticmethod
    def _update_pipeline_status(
        pipeline_id: str | None, workflow_execution: WorkflowExecution
    ) -> None:
        try:
            if pipeline_id:
                # Update pipeline status
                if workflow_execution.status != ExecutionStatus.ERROR.value:
                    PipelineProcessor.update_pipeline(
                        pipeline_id,
                        Pipeline.PipelineStatus.SUCCESS,
                        execution_id=workflow_execution.id,
                        is_end=True,
                    )
                else:
                    PipelineProcessor.update_pipeline(
                        pipeline_id,
                        Pipeline.PipelineStatus.FAILURE,
                        execution_id=workflow_execution.id,
                        error_message=workflow_execution.error_message,
                        is_end=True,
                    )
        # Expected exception since API deployments are not tracked in Pipeline
        except Pipeline.DoesNotExist:
            api = APIDeploymentUtils.get_api_by_id(api_id=pipeline_id)
            if api:
                APIDeploymentUtils.send_notification(
                    api=api, workflow_execution=workflow_execution
                )
        except Exception as e:
            logger.warning(
                f"Error updating pipeline {pipeline_id} status: {e}, "
                f"with workflow execution: {workflow_execution}"
            )

    @classmethod
    def get_status_of_async_task(
        cls,
        execution_id: str,
    ) -> ExecutionResponse:
        """Get celery task status.

        Args:
            execution_id (str): workflow execution id

        Raises:
            TaskDoesNotExistError: Not found exception
            ExecutionDoesNotExistError: If execution is not found

        Returns:
            ExecutionResponse: _description_
        """
        execution: WorkflowExecution = WorkflowExecution.objects.get(id=execution_id)
        if not execution.task_id:
            raise TaskDoesNotExistError(f"No task ID found for execution: {execution_id}")

        task_result = None
        result_acknowledged = execution.result_acknowledged
        # Prepare the initial response with the task's current status and result.
        if execution.is_completed:
            task_result = ResultCacheUtils.get_api_results(
                workflow_id=str(execution.workflow.id), execution_id=execution_id
            )
            cls._set_result_acknowledge(execution)

        result_response = ExecutionResponse(
            workflow_id=str(execution.workflow.id),
            execution_id=execution_id,
            execution_status=execution.status,
            result=task_result,
            result_acknowledged=result_acknowledged,
        )
        return result_response

    @staticmethod
    def _set_result_acknowledge(execution: WorkflowExecution) -> None:
        """Mark the result as acknowledged and update the database.

        This method is called once the task has completed and its result is forgotten.
        It ensures that the task result is flagged as acknowledged in the database

        Args:
            execution (WorkflowExecution): WorkflowExecution instance
        """
        if not execution.result_acknowledged:
            execution.result_acknowledged = True
            execution.save()
            logger.info(
                f"ExecutionID [{execution.id}] - Task {execution.task_id} acknowledged"
            )
        # Delete api results from cache
        ResultCacheUtils.delete_api_results(
            workflow_id=str(execution.workflow.id), execution_id=str(execution.id)
        )
        ExecutionCacheUtils.delete_execution(
            workflow_id=str(execution.workflow.id), execution_id=str(execution.id)
        )

    @classmethod
    def _get_execution_status(
        cls, workflow_id: str, execution_id: str
    ) -> ExecutionStatus:
        execution_cache = ExecutionCacheUtils.get_execution(
            workflow_id=workflow_id, execution_id=execution_id
        )
        if not execution_cache:
            execution_model: WorkflowExecution = WorkflowExecution.objects.get(
                id=execution_id
            )
            execution_cache = ExecutionCache(
                workflow_id=workflow_id,
                execution_id=execution_id,
                status=ExecutionStatus(execution_model.status),
                total_files=execution_model.total_files,
                completed_files=execution_model.completed_files,
                failed_files=execution_model.failed_files,
            )
            ExecutionCacheUtils.create_execution(
                execution=execution_cache,
            )
        return execution_cache.status

    @classmethod
    def execute_workflow_async(
        cls,
        workflow_id: str,
        execution_id: str,
        hash_values_of_files: dict[str, FileHash],
        timeout: int = -1,
        pipeline_id: str | None = None,
        queue: str | None = None,
        use_file_history: bool = True,
    ) -> ExecutionResponse:
        """Adding a workflow to the queue for execution.

        Args:
            workflow_id (str): workflowId
            execution_id (str): Execution ID
            timeout (int):  Celery timeout (timeout -1 : async execution)
            pipeline_id (Optional[str], optional): Optional pipeline. Defaults to None.
            queue (Optional[str]): Name of the celery queue to push into
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to True

        Returns:
            ExecutionResponse: Existing status of execution
        """
        try:
            file_hash_in_str = {
                key: value.to_json() for key, value in hash_values_of_files.items()
            }
            org_schema = UserContext.get_organization_identifier()
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            async_execution: AsyncResult = celery_app.send_task(
                "async_execute_bin",
                args=[
                    org_schema,  # schema_name
                    workflow_id,  # workflow_id
                    execution_id,  # execution_id
                    file_hash_in_str,  # hash_values_of_files
                ],
                kwargs={
                    "scheduled": False,
                    "execution_mode": None,
                    "pipeline_id": pipeline_id,
                    "log_events_id": log_events_id,
                    "use_file_history": use_file_history,
                },
                queue=queue,
            )
            logger.info(
                f"[{org_schema}] Job '{async_execution}' has been enqueued for "
                f"execution_id '{execution_id}', '{len(hash_values_of_files)}' files"
            )
            workflow_execution: WorkflowExecution = WorkflowExecution.objects.get(
                id=execution_id
            )
            workflow_execution.task_id = async_execution.id
            workflow_execution.save()
            execution_status = workflow_execution.status
            if timeout > -1:
                while not ExecutionStatus.is_completed(execution_status) and timeout > 0:
                    time.sleep(2)
                    timeout -= 2

                    execution_status = cls._get_execution_status(
                        workflow_id=workflow_id, execution_id=execution_id
                    )
            if ExecutionStatus.is_completed(execution_status):
                # Fetch the object agian to get the latest status.
                workflow_execution: WorkflowExecution = WorkflowExecution.objects.get(
                    id=execution_id
                )
                task_result = ResultCacheUtils.get_api_results(
                    workflow_id=workflow_id, execution_id=execution_id
                )
                cls._set_result_acknowledge(workflow_execution)
            else:
                task_result = None
            execution_response = ExecutionResponse(
                workflow_id,
                execution_id,
                execution_status,
                result=task_result,
            )
            return execution_response
        except celery_exceptions.TimeoutError:
            return ExecutionResponse(
                workflow_id,
                execution_id,
                async_execution.status,
                message=WorkflowMessages.CELERY_TIMEOUT_MESSAGE,
            )
        except Exception as error:
            WorkflowExecutionServiceHelper.update_execution_err(execution_id, str(error))
            logger.error(
                f"Error while enqueuing async job for WF '{workflow_id}', "
                f"execution '{execution_id}': {str(error)}",
                exc_info=True,
                stack_info=True,
            )
            return ExecutionResponse(
                workflow_id,
                execution_id,
                ExecutionStatus.ERROR.value,
                error=str(error),
            )

    @staticmethod
    @celery_app.task(
        name="async_execute_bin",
        autoretry_for=(Exception,),
        max_retries=0,
        retry_backoff=True,
        retry_backoff_max=500,
        retry_jitter=True,
    )
    def execute_bin(
        schema_name: str,
        workflow_id: str,
        execution_id: str,
        hash_values_of_files: dict[str, dict[str, Any]],
        scheduled: bool = False,
        execution_mode: tuple[str, str] | None = None,
        pipeline_id: str | None = None,
        use_file_history: bool = True,
        **kwargs: dict[str, Any],
    ) -> list[Any] | None:
        """Asynchronous Execution By celery.

        Args:
            schema_name (str): schema name to get Data
            workflow_id (str): Workflow Id
            execution_id (str): Id of the execution
            scheduled (bool, optional): Represents if it is a scheduled execution
                Defaults to False
            execution_mode (Optional[WorkflowExecution.Mode]): WorkflowExecution Mode
                Defaults to None
            pipeline_id (Optional[str], optional): Id of pipeline. Defaults to None
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to True

        Kwargs:
            log_events_id (str): Session ID of the user,
                helps establish WS connection for streaming logs to the FE

        Returns:
            dict[str, list[Any]]: Returns a dict with result from workflow execution
        """
        task_id = current_task.request.id
        # Set organization in state store for execution
        StateStore.set(Account.ORGANIZATION_ID, schema_name)
        WorkflowHelper.execute_workflow(
            organization_id=schema_name,
            task_id=task_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            hash_values_of_files=hash_values_of_files,
            scheduled=scheduled,
            execution_mode=execution_mode,
            pipeline_id=pipeline_id,
            use_file_history=use_file_history,
            **kwargs,
        )

    @staticmethod
    def execute_workflow(
        organization_id: str,
        task_id: str,
        workflow_id: str,
        execution_id: str,
        hash_values_of_files: dict[str, str],
        scheduled: bool = False,
        execution_mode: tuple[str, str] | None = None,
        pipeline_id: str | None = None,
        use_file_history: bool = True,
        **kwargs: dict[str, Any],
    ) -> list[Any] | None:
        """Asynchronous Execution By celery.

        Args:
            schema_name (str): schema name to get Data
            workflow_id (str): Workflow Id
            execution_id (Optional[str], optional): Id of the execution.
                Defaults to None.
            scheduled (bool, optional): Represents if it is a scheduled
                execution. Defaults to False.
            execution_mode (Optional[WorkflowExecution.Mode]):
                WorkflowExecution Mode. Defaults to None.
            pipeline_id (Optional[str], optional): Id of pipeline.
                Defaults to None.
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to True

        Kwargs:
            log_events_id (str): Session ID of the user, helps establish
                WS connection for streaming logs to the FE

        Returns:
            dict[str, list[Any]]: Returns a dict with result from
                workflow execution
        """
        logger.info(
            f"Executing for execution_id: {execution_id}, task_id: {task_id}, "
            f"org: {organization_id}, workflow_id: {workflow_id}, "
            f"files: {len(hash_values_of_files)}"
        )
        hash_values = {
            key: FileHash.from_json(value) for key, value in hash_values_of_files.items()
        }
        workflow = Workflow.objects.get(id=workflow_id)
        # TODO: Make use of WorkflowExecution.get_or_create()
        try:
            workflow_execution = WorkflowExecutionServiceHelper.create_workflow_execution(
                workflow_id=workflow_id,
                single_step=False,
                pipeline_id=pipeline_id,
                mode=WorkflowExecution.Mode.QUEUE,
                execution_id=execution_id,
                total_files=len(hash_values),
                **kwargs,  # type: ignore
            )
        except IntegrityError:
            # Use existing instance on retry attempt
            workflow_execution = WorkflowExecution.objects.get(pk=execution_id)
        WorkflowExecutionServiceHelper.update_execution_task(
            execution_id=execution_id, task_id=task_id
        )
        try:
            execution_response = WorkflowHelper.run_workflow(
                workflow=workflow,
                organization_id=organization_id,
                pipeline_id=pipeline_id,
                scheduled=scheduled,
                workflow_execution=workflow_execution,
                execution_mode=execution_mode,
                hash_values_of_files=hash_values,
                use_file_history=use_file_history,
            )
        except Exception as error:
            error_message = traceback.format_exc()
            logger.error(
                f"Error executing execution {workflow_execution}: {error_message}"
            )
            WorkflowExecutionServiceHelper.update_execution_err(execution_id, str(error))
            raise
        return execution_response.result

    @staticmethod
    def complete_execution(
        workflow: Workflow,
        execution_id: str | None = None,
        pipeline_id: str | None = None,
        execution_mode: WorkflowExecution | None = WorkflowExecution.Mode.QUEUE,
        hash_values_of_files: dict[str, FileHash] = {},
        use_file_history: bool = False,
    ) -> ExecutionResponse:
        if pipeline_id:
            logger.info(f"Executing pipeline: {pipeline_id}")
            # Create a new WorkflowExecution entity for each pipeline execution.
            # This ensures every pipeline run is tracked as a distinct execution.
            workflow_execution = WorkflowExecutionServiceHelper.create_workflow_execution(
                workflow_id=workflow.id,
                single_step=False,
                pipeline_id=pipeline_id,
                mode=execution_mode,
                total_files=len(hash_values_of_files),
            )
            execution_id = workflow_execution.id
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            org_schema = UserContext.get_organization_identifier()
            if execution_mode == WorkflowExecution.Mode.INSTANT:
                # Instant request from UX (Sync now in ETL and Workflow page)
                response: ExecutionResponse = WorkflowHelper.execute_workflow_async(
                    workflow_id=workflow.id,
                    pipeline_id=pipeline_id,
                    execution_id=execution_id,
                    hash_values_of_files=hash_values_of_files,
                    use_file_history=use_file_history,
                )
                return response
            else:
                task_id = current_task.request.id
                # TODO: Remove this if scheduled runs work
                StateStore.set(Account.ORGANIZATION_ID, org_schema)
                execution_result = WorkflowHelper.execute_workflow(
                    organization_id=org_schema,
                    task_id=task_id,
                    workflow_id=workflow.id,
                    execution_id=workflow_execution.id,
                    hash_values_of_files=hash_values_of_files,
                    scheduled=True,
                    execution_mode=execution_mode,
                    pipeline_id=pipeline_id,
                    use_file_history=use_file_history,
                    log_events_id=log_events_id,
                )
                ExecutionCacheUtils.delete_execution(
                    workflow_id=str(workflow.id), execution_id=str(execution_id)
                )
            updated_execution = WorkflowExecution.objects.get(id=execution_id)
            execution_response = ExecutionResponse(
                workflow.id,
                execution_id,
                updated_execution.status,
                result=execution_result,
            )
            return execution_response

        if execution_id is None:
            # Creating execution entity and return
            return WorkflowHelper.create_and_make_execution_response(
                workflow_id=workflow.id, pipeline_id=pipeline_id
            )
        try:
            # Normal execution
            workflow_execution = WorkflowExecution.objects.get(pk=execution_id)
            if (
                workflow_execution.status != ExecutionStatus.PENDING
                or workflow_execution.execution_type != WorkflowExecution.Type.COMPLETE
            ):
                raise InvalidRequest(WorkflowErrors.INVALID_EXECUTION_ID)
            return WorkflowHelper.run_workflow(
                workflow=workflow,
                workflow_execution=workflow_execution,
                hash_values_of_files=hash_values_of_files,
                use_file_history=use_file_history,
            )
        except WorkflowExecution.DoesNotExist:
            return WorkflowHelper.create_and_make_execution_response(
                workflow_id=workflow.id, pipeline_id=pipeline_id
            )

    @staticmethod
    def get_current_execution(execution_id: str) -> ExecutionResponse:
        try:
            workflow_execution = WorkflowExecution.objects.get(pk=execution_id)
            return ExecutionResponse(
                workflow_execution.workflow_id,
                workflow_execution.id,
                workflow_execution.status,
                log_id=workflow_execution.execution_log_id,
                error=workflow_execution.error_message,
                mode=workflow_execution.execution_mode,
            )
        except WorkflowExecution.DoesNotExist:
            raise WorkflowExecutionNotExist()

    @staticmethod
    def step_execution(
        workflow: Workflow,
        execution_action: str,
        execution_id: str | None = None,
        hash_values_of_files: dict[str, FileHash] = {},
    ) -> ExecutionResponse:
        if execution_action is Workflow.ExecutionAction.START.value:  # type: ignore
            if execution_id is None:
                return WorkflowHelper.create_and_make_execution_response(
                    workflow_id=workflow.id, single_step=True
                )
            try:
                workflow_execution = WorkflowExecution.objects.get(pk=execution_id)
                return WorkflowHelper.run_workflow(
                    workflow=workflow,
                    single_step=True,
                    workflow_execution=workflow_execution,
                    hash_values_of_files=hash_values_of_files,
                )
            except WorkflowExecution.DoesNotExist:
                return WorkflowHelper.create_and_make_execution_response(
                    workflow_id=workflow.id, single_step=True
                )

        else:
            if execution_id is None:
                raise InvalidRequest("execution_id is missed")
            try:
                workflow_execution = WorkflowExecution.objects.get(pk=execution_id)
            except WorkflowExecution.DoesNotExist:
                raise WorkflowExecutionNotExist(WorkflowErrors.INVALID_EXECUTION_ID)
            if (
                workflow_execution.status != ExecutionStatus.PENDING
                or workflow_execution.execution_type != WorkflowExecution.Type.STEP
            ):
                raise InvalidRequest(WorkflowErrors.INVALID_EXECUTION_ID)
            current_action: str | None = CacheService.get_key(execution_id)
            logger.info(f"workflow_execution.current_action {current_action}")
            if current_action is None:
                raise InvalidRequest(WorkflowErrors.INVALID_EXECUTION_ID)
            CacheService.set_key(execution_id, execution_action)
            workflow_execution = WorkflowExecution.objects.get(pk=execution_id)

            return ExecutionResponse(
                workflow.id,
                execution_id,
                workflow_execution.status,
                log_id=workflow_execution.execution_log_id,
                error=workflow_execution.error_message,
                mode=workflow_execution.execution_mode,
            )

    @staticmethod
    def create_and_make_execution_response(
        workflow_id: str,
        pipeline_id: str | None = None,
        single_step: bool = False,
        mode: tuple[str, str] = WorkflowExecution.Mode.INSTANT,
    ) -> ExecutionResponse:
        log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
        workflow_execution = WorkflowExecutionServiceHelper.create_workflow_execution(
            workflow_id=workflow_id,
            single_step=single_step,
            pipeline_id=pipeline_id,
            mode=mode,
            log_events_id=log_events_id,
        )
        return ExecutionResponse(
            workflow_execution.workflow_id,
            workflow_execution.id,
            workflow_execution.status,
            log_id=workflow_execution.execution_log_id,
            error=workflow_execution.error_message,
            mode=workflow_execution.execution_mode,
        )

    # TODO: Access cache through a manager
    @staticmethod
    def clear_cache(workflow_id: str) -> dict[str, Any]:
        """Function to clear cache with a specific pattern."""
        response: dict[str, Any] = {}
        try:
            key_pattern = f"*:cache:{workflow_id}:*"
            CacheService.clear_cache(key_pattern)
            response["message"] = WorkflowMessages.CACHE_CLEAR_SUCCESS
            response["status"] = 200
            return response
        except Exception as exc:
            logger.error(f"Error occurred while clearing cache : {exc}")
            response["message"] = WorkflowMessages.CACHE_CLEAR_FAILED
            response["status"] = 400
            return response

    @staticmethod
    def clear_file_marker(workflow_id: str) -> dict[str, Any]:
        """Function to clear file marker from the cache."""
        # Clear file history from the table
        response: dict[str, Any] = {}
        workflow = Workflow.objects.get(id=workflow_id)
        try:
            FileHistoryHelper.clear_history_for_workflow(workflow=workflow)
            response["message"] = WorkflowMessages.FILE_MARKER_CLEAR_SUCCESS
            response["status"] = 200
            return response
        except Exception as exc:
            logger.error(f"Error occurred while clearing file marker : {exc}")
            response["message"] = WorkflowMessages.FILE_MARKER_CLEAR_FAILED
            response["status"] = 400
            return response

    @staticmethod
    def get_workflow_execution_id(execution_id: str) -> str:
        wf_exec_prefix = WorkflowExecutionKey.WORKFLOW_EXECUTION_ID_PREFIX
        workflow_execution_id = f"{wf_exec_prefix}-{execution_id}"
        return workflow_execution_id

    @staticmethod
    def get_execution_by_id(execution_id: str) -> WorkflowExecution:
        try:
            execution: WorkflowExecution = WorkflowExecution.objects.get(id=execution_id)
            return execution
        except WorkflowExecution.DoesNotExist:
            raise WorkflowDoesNotExistError()

    @staticmethod
    def make_async_result(obj: AsyncResult) -> dict[str, Any]:
        return {
            "id": obj.id,
            "status": obj.status,
            "result": obj.result,
            "is_ready": obj.ready(),
            "is_failed": obj.failed(),
            "info": obj.info,
        }

    @staticmethod
    def can_update_workflow(workflow_id: str) -> dict[str, Any]:
        try:
            workflow: Workflow = Workflow.objects.get(pk=workflow_id)
            if not workflow or workflow is None:
                raise WorkflowDoesNotExistError()
            used_count = Pipeline.objects.filter(workflow=workflow).count()
            if used_count == 0:
                used_count = APIDeployment.objects.filter(workflow=workflow).count()
            return {"can_update": used_count == 0}
        except Workflow.DoesNotExist:
            logger.error(f"Error getting workflow: {id}")
            raise WorkflowDoesNotExistError()


class WorkflowSchemaHelper:
    """Helper class for workflow schema related methods."""

    @staticmethod
    def validate_request(schema_type: SchemaType, schema_entity: SchemaEntity) -> bool:
        """Validates the given args for reading the JSON schema.

        Schema type of `src`, allows entities `file` and `api`
        Schema type of `dest`, allows entities `db`

        Args:
            schema_type (SchemaType): Enum with values `src`, `dest`
            schema_entity (SchemaEntity): Enum with values `file`, `api`, `db`

        Raises:
            serializers.ValidationError: If invalid values/
                combination is requested

        Returns:
            bool: _description_
        """
        possible_types = [e.value for e in SchemaType]
        possible_entities = [e.value for e in SchemaEntity]

        if schema_type.value not in possible_types:
            raise serializers.ValidationError(
                f"Invalid value for 'type': {schema_type.value}, "
                f"should be one of {possible_types}"
            )

        if schema_entity.value not in possible_entities:
            raise serializers.ValidationError(
                f"Invalid value for 'entity': {schema_entity.value}, "
                f"should be one of {possible_entities}"
            )

        if (schema_type == SchemaType.SRC and schema_entity == SchemaEntity.DB) or (
            schema_type == SchemaType.DEST and schema_entity != SchemaEntity.DB
        ):
            raise serializers.ValidationError(
                f"Invalid values for 'type': {schema_type.value}, "
                f"'entity': {schema_entity.value}."
                f"Param 'type': {SchemaType.SRC.value} allows "
                f"{SchemaEntity.FILE.value} and {SchemaEntity.API.value}"
                f"'type': {SchemaType.DEST.value} allows "
                f"{SchemaEntity.DB.value}."
            )
        return True

    @staticmethod
    def get_json_schema(
        schema_type: SchemaType, schema_entity: SchemaEntity
    ) -> dict[str, Any]:
        """Reads and returns the JSON schema for the given args.

        Args:
            schema_type (SchemaType): Enum with values `src`, `dest`
            schema_entity (SchemaEntity): Enum with values `file`, `api`, `db`

        Returns:
            dict[str, Any]: JSON schema for the requested entity
        """
        schema_path = (
            f"{os.path.dirname(__file__)}/static/{schema_type}/{schema_entity}.json"
        )
        with open(schema_path, encoding="utf-8") as file:
            schema = json.load(file)
        return schema  # type: ignore
