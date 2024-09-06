import json
import logging
import os
import traceback
from typing import Any, Optional

from account.constants import Common
from account.models import Organization
from api.models import APIDeployment
from api.utils import APIDeploymentUtils
from celery import current_task
from celery import exceptions as celery_exceptions
from celery import shared_task
from celery.result import AsyncResult
from django.db import IntegrityError, connection
from django_tenants.utils import get_tenant_model, tenant_context
from pipeline.models import Pipeline
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework import serializers
from tool_instance.constants import ToolInstanceKey
from tool_instance.models import ToolInstance
from tool_instance.tool_instance_helper import ToolInstanceHelper
from unstract.workflow_execution.enums import LogComponent, LogLevel, LogState
from unstract.workflow_execution.exceptions import StopExecution
from utils.cache_service import CacheService
from utils.local_context import StateStore
from workflow_manager.endpoint.destination import DestinationConnector
from workflow_manager.endpoint.dto import FileHash
from workflow_manager.endpoint.source import SourceConnector
from workflow_manager.workflow.constants import (
    CeleryConfigurations,
    WorkflowErrors,
    WorkflowExecutionKey,
    WorkflowMessages,
)
from workflow_manager.workflow.dto import AsyncResultData, ExecutionResponse
from workflow_manager.workflow.enums import ExecutionStatus, SchemaEntity, SchemaType
from workflow_manager.workflow.exceptions import (
    InvalidRequest,
    TaskDoesNotExistError,
    WorkflowDoesNotExistError,
    WorkflowExecutionNotExist,
)
from workflow_manager.workflow.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow.file_history_helper import FileHistoryHelper
from workflow_manager.workflow.models.execution import WorkflowExecution
from workflow_manager.workflow.models.workflow import Workflow
from workflow_manager.workflow.utils import WorkflowUtil

logger = logging.getLogger(__name__)


class WorkflowHelper:
    @staticmethod
    def get_workflow_by_id(id: str) -> Workflow:
        try:
            workflow: Workflow = Workflow.objects.get(pk=id)
            if not workflow or workflow is None:
                raise WorkflowDoesNotExistError()
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

    @staticmethod
    def build_workflow_execution_service(
        organization_id: Optional[str],
        workflow: Workflow,
        tool_instances: list[ToolInstance],
        pipeline_id: Optional[str],
        single_step: bool,
        scheduled: bool,
        execution_mode: tuple[str, str],
        workflow_execution: Optional[WorkflowExecution],
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
        )
        workflow_execution_service.build()
        return workflow_execution_service

    @staticmethod
    def process_input_files(
        workflow: Workflow,
        source: SourceConnector,
        destination: DestinationConnector,
        execution_service: WorkflowExecutionServiceHelper,
        single_step: bool,
        hash_values_of_files: dict[str, FileHash] = {},
    ) -> WorkflowExecution:
        input_files, total_files = source.list_files_from_source(hash_values_of_files)
        error_message = None
        successful_files = 0
        failed_files = 0
        execution_service.publish_initial_workflow_logs(total_files)
        execution_service.update_execution(
            ExecutionStatus.EXECUTING, increment_attempt=True
        )
        if total_files > 0:
            q_file_no_list = WorkflowUtil.get_q_no_list(workflow, total_files)

        for index, (file_path, file_hash) in enumerate(input_files.items()):
            file_number = index + 1
            file_hash = WorkflowUtil.add_file_destination_filehash(
                file_number,
                q_file_no_list,
                file_hash,
            )
            try:
                error = WorkflowHelper.process_file(
                    current_file_idx=file_number,
                    total_files=total_files,
                    input_file=file_hash.file_path,
                    workflow=workflow,
                    source=source,
                    destination=destination,
                    execution_service=execution_service,
                    single_step=single_step,
                    file_hash=file_hash,
                )
                if error:
                    failed_files += 1
                else:
                    successful_files += 1
            except StopExecution as e:
                execution_service.update_execution(
                    ExecutionStatus.STOPPED, error=str(e)
                )
                break
            except Exception as e:
                failed_files += 1
                error_message = f"Error processing file '{file_path}'. {e}"
                execution_service.publish_log(
                    message=error_message, level=LogLevel.ERROR
                )
        if failed_files and failed_files >= total_files:
            execution_service.update_execution(
                ExecutionStatus.ERROR, error=error_message
            )
        else:
            execution_service.update_execution(ExecutionStatus.COMPLETED)

        execution_service.publish_final_workflow_logs(
            total_files=total_files,
            successful_files=successful_files,
            failed_files=failed_files,
        )
        return execution_service.get_execution_instance()

    @staticmethod
    def process_file(
        current_file_idx: int,
        total_files: int,
        input_file: str,
        workflow: Workflow,
        source: SourceConnector,
        destination: DestinationConnector,
        execution_service: WorkflowExecutionServiceHelper,
        single_step: bool,
        file_hash: FileHash,
    ) -> Optional[str]:
        error: Optional[str] = None
        file_name = source.add_file_to_volume(
            input_file_path=input_file, file_hash=file_hash
        )
        try:
            execution_service.initiate_tool_execution(
                current_file_idx, total_files, file_name, single_step
            )
            if not file_hash.is_executed:
                execution_service.execute_input_file(
                    file_name=file_name,
                    single_step=single_step,
                )
        except StopExecution:
            raise
        except Exception as e:
            error = f"Error processing file {input_file}: {str(e)}"
            execution_service.publish_log(error, level=LogLevel.ERROR)
        execution_service.publish_update_log(
            LogState.RUNNING,
            f"Processing output for {file_name}",
            LogComponent.DESTINATION,
        )
        destination.handle_output(
            file_name=file_name,
            file_hash=file_hash,
            workflow=workflow,
            error=error,
            input_file_path=input_file,
        )
        execution_service.publish_update_log(
            LogState.SUCCESS,
            f"{file_name}'s output is processed successfully",
            LogComponent.DESTINATION,
        )
        return error

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
        hash_values_of_files: dict[str, FileHash] = {},
        organization_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        scheduled: bool = False,
        single_step: bool = False,
        workflow_execution: Optional[WorkflowExecution] = None,
        execution_mode: Optional[tuple[str, str]] = None,
    ) -> ExecutionResponse:
        tool_instances: list[ToolInstance] = (
            ToolInstanceHelper.get_tool_instances_by_workflow(
                workflow.id, ToolInstanceKey.STEP
            )
        )

        WorkflowHelper.validate_tool_instances_meta(tool_instances=tool_instances)
        execution_mode = execution_mode or WorkflowExecution.Mode.INSTANT
        execution_service = WorkflowHelper.build_workflow_execution_service(
            organization_id=organization_id,
            workflow=workflow,
            tool_instances=tool_instances,
            pipeline_id=pipeline_id,
            single_step=single_step,
            scheduled=scheduled,
            execution_mode=execution_mode,
            workflow_execution=workflow_execution,
        )
        execution_id = execution_service.execution_id
        source = SourceConnector(
            organization_id=organization_id,
            workflow=workflow,
            execution_id=execution_id,
            execution_service=execution_service,
        )
        destination = DestinationConnector(
            workflow=workflow,
            execution_id=execution_id,
            execution_service=execution_service,
        )
        # Validating endpoints
        source.validate()
        destination.validate()
        # Execution Process
        try:
            workflow_execution = WorkflowHelper.process_input_files(
                workflow,
                source,
                destination,
                execution_service,
                single_step=single_step,
                hash_values_of_files=hash_values_of_files,
            )
            WorkflowHelper._update_pipeline_status(
                pipeline_id=pipeline_id, workflow_execution=workflow_execution
            )
            return ExecutionResponse(
                str(workflow.id),
                str(workflow_execution.id),
                workflow_execution.status,
                log_id=str(execution_service.execution_log_id),
                error=workflow_execution.error_message,
                mode=workflow_execution.execution_mode,
                result=destination.api_results,
            )
        except Exception as e:
            logger.error(f"Error executing workflow {workflow}: {e}")
            logger.error(f"Error {traceback.format_exc()}")
            workflow_execution = WorkflowExecutionServiceHelper.update_execution_err(
                execution_id, str(e)
            )
            WorkflowHelper._update_pipeline_status(
                pipeline_id=pipeline_id, workflow_execution=workflow_execution
            )
            raise
        finally:
            destination.delete_execution_directory()

    @staticmethod
    def _update_pipeline_status(
        pipeline_id: Optional[str], workflow_execution: WorkflowExecution
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

    @staticmethod
    def get_status_of_async_task(
        execution_id: str,
    ) -> ExecutionResponse:
        """Get celery task status.

        Args:
            execution_id (str): workflow execution id

        Raises:
            TaskDoesNotExistError: Not found exception

        Returns:
            ExecutionResponse: _description_
        """
        execution = WorkflowExecution.objects.get(id=execution_id)

        if not execution.task_id:
            raise TaskDoesNotExistError()

        result = AsyncResult(str(execution.task_id))

        task = AsyncResultData(async_result=result)
        return ExecutionResponse(
            execution.workflow_id,
            execution_id,
            execution.status,
            result=task.result,
        )

    @staticmethod
    def execute_workflow_async(
        workflow_id: str,
        execution_id: str,
        hash_values_of_files: dict[str, FileHash],
        timeout: int = -1,
        pipeline_id: Optional[str] = None,
        queue: Optional[str] = None,
    ) -> ExecutionResponse:
        """Adding a workflow to the queue for execution.

        Args:
            workflow_id (str): workflowId
            execution_id (str): Execution ID
            timeout (int):  Celery timeout (timeout -1 : async execution)
            pipeline_id (Optional[str], optional): Optional pipeline. Defaults to None.

        Returns:
            ExecutionResponse: Existing status of execution
        """
        try:
            file_hash_in_str = {
                key: value.to_json() for key, value in hash_values_of_files.items()
            }
            org_schema = connection.tenant.schema_name
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            async_execution = WorkflowHelper.execute_bin.apply_async(
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
                },
                queue=queue,
            )
            if timeout > -1:
                async_execution.wait(
                    timeout=timeout,
                    interval=CeleryConfigurations.INTERVAL,
                )
            task = AsyncResultData(async_result=async_execution)
            logger.info(f"Job {async_execution} enqueued.")
            celery_result = task.to_dict()
            task_result = celery_result.get("result")
            workflow_execution = WorkflowExecution.objects.get(id=execution_id)
            execution_response = ExecutionResponse(
                workflow_id,
                execution_id,
                workflow_execution.status,
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
            WorkflowExecutionServiceHelper.update_execution_err(
                execution_id, str(error)
            )
            logger.error(f"Errors while job enqueueing {str(error)}")
            logger.error(f"Error {traceback.format_exc()}")
            return ExecutionResponse(
                workflow_id,
                execution_id,
                ExecutionStatus.ERROR.value,
                error=str(error),
            )

    @staticmethod
    @shared_task(
        name="async_execute_bin",
        acks_late=True,
        autoretry_for=(Exception,),
        max_retries=1,
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
        execution_mode: Optional[tuple[str, str]] = None,
        pipeline_id: Optional[str] = None,
        **kwargs: dict[str, Any],
    ) -> Optional[list[Any]]:
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

        Kwargs:
            log_events_id (str): Session ID of the user,
                helps establish WS connection for streaming logs to the FE

        Returns:
            dict[str, list[Any]]: Returns a dict with result from workflow execution
        """
        hash_values = {
            key: FileHash.from_json(value)
            for key, value in hash_values_of_files.items()
        }
        task_id = current_task.request.id
        tenant: Organization = (
            get_tenant_model().objects.filter(schema_name=schema_name).first()
        )
        with tenant_context(tenant):
            workflow = Workflow.objects.get(id=workflow_id)
            try:
                workflow_execution = (
                    WorkflowExecutionServiceHelper.create_workflow_execution(
                        workflow_id=workflow_id,
                        single_step=False,
                        pipeline_id=pipeline_id,
                        mode=WorkflowExecution.Mode.QUEUE,
                        execution_id=execution_id,
                        **kwargs,  # type: ignore
                    )
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
                    organization_id=schema_name,
                    pipeline_id=pipeline_id,
                    scheduled=scheduled,
                    workflow_execution=workflow_execution,
                    execution_mode=execution_mode,
                    hash_values_of_files=hash_values,
                )
            except Exception as e:
                return ExecutionResponse(
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    execution_status=ExecutionStatus.ERROR.value,
                    error=str(e),
                )
            return execution_response.result

    @staticmethod
    def complete_execution(
        workflow: Workflow,
        execution_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        execution_mode: Optional[WorkflowExecution] = WorkflowExecution.Mode.QUEUE,
        hash_values_of_files: dict[str, FileHash] = {},
    ) -> ExecutionResponse:
        if pipeline_id:
            logger.info(f"Executing pipeline: {pipeline_id}")
            # Create a new WorkflowExecution entity for each pipeline execution.
            # This ensures every pipeline run is tracked as a distinct execution.
            workflow_execution = (
                WorkflowExecutionServiceHelper.create_workflow_execution(
                    workflow_id=workflow.id,
                    single_step=False,
                    pipeline_id=pipeline_id,
                    mode=execution_mode,
                )
            )
            execution_id = workflow_execution.id
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            org_schema = connection.tenant.schema_name
            if execution_mode == WorkflowExecution.Mode.INSTANT:
                # Instant request from UX (Sync now in ETL and Workflow page)
                response: ExecutionResponse = WorkflowHelper.execute_workflow_async(
                    workflow_id=workflow.id,
                    pipeline_id=pipeline_id,
                    execution_id=execution_id,
                    hash_values_of_files=hash_values_of_files,
                )
                return response
            else:
                execution_result = WorkflowHelper.execute_bin(
                    schema_name=org_schema,
                    workflow_id=workflow.id,
                    execution_id=workflow_execution.id,
                    hash_values_of_files=hash_values_of_files,
                    scheduled=True,
                    execution_mode=execution_mode,
                    pipeline_id=pipeline_id,
                    log_events_id=log_events_id,
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
                workflow_execution.status != ExecutionStatus.PENDING.value
                or workflow_execution.execution_type != WorkflowExecution.Type.COMPLETE
            ):
                raise InvalidRequest(WorkflowErrors.INVALID_EXECUTION_ID)
            return WorkflowHelper.run_workflow(
                workflow=workflow,
                workflow_execution=workflow_execution,
                hash_values_of_files=hash_values_of_files,
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
        execution_id: Optional[str] = None,
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
                workflow_execution.status != ExecutionStatus.PENDING.value
                or workflow_execution.execution_type != WorkflowExecution.Type.STEP
            ):
                raise InvalidRequest(WorkflowErrors.INVALID_EXECUTION_ID)
            current_action: Optional[str] = CacheService.get_key(execution_id)
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
        pipeline_id: Optional[str] = None,
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
            execution: WorkflowExecution = WorkflowExecution.objects.get(
                id=execution_id
            )
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
            f"{os.path.dirname(__file__)}/static/" f"{schema_type}/{schema_entity}.json"
        )
        with open(schema_path, encoding="utf-8") as file:
            schema = json.load(file)
        return schema  # type: ignore
