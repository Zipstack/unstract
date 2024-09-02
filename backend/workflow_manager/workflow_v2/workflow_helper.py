import json
import logging
import os
import traceback
import uuid
from typing import Any, Optional

from account_v2.constants import Common
from api_v2.models import APIDeployment
from celery import current_task
from celery import exceptions as celery_exceptions
from celery import shared_task
from celery.result import AsyncResult
from django.db import IntegrityError
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers
from tool_instance_v2.constants import ToolInstanceKey
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from unstract.workflow_execution.enums import LogComponent, LogLevel, LogState
from unstract.workflow_execution.exceptions import StopExecution
from utils.cache_service import CacheService
from utils.constants import Account
from utils.local_context import StateStore
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.workflow_v2.constants import (
    CeleryConfigurations,
    WorkflowErrors,
    WorkflowExecutionKey,
    WorkflowMessages,
)
from workflow_manager.workflow_v2.dto import AsyncResultData, ExecutionResponse
from workflow_manager.workflow_v2.enums import ExecutionStatus, SchemaEntity, SchemaType
from workflow_manager.workflow_v2.exceptions import (
    InvalidRequest,
    TaskDoesNotExistError,
    WorkflowDoesNotExistError,
    WorkflowExecutionNotExist,
)
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.file_history_helper import FileHistoryHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

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
        include_metadata: bool = False,
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
            include_metadata=include_metadata,
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
        hash_values_of_files: dict[str, str] = {},
    ) -> WorkflowExecution:
        input_files = source.list_files_from_source()
        total_files = len(input_files)
        processed_files = 0
        error_raised = 0
        execution_service.publish_initial_workflow_logs(total_files)
        execution_service.update_execution(
            ExecutionStatus.EXECUTING, increment_attempt=True
        )
        for index, input_file in enumerate(input_files):
            file_number = index + 1
            try:
                is_executed, error = WorkflowHelper.process_file(
                    current_file_idx=file_number,
                    total_files=total_files,
                    input_file=input_file,
                    workflow=workflow,
                    source=source,
                    destination=destination,
                    execution_service=execution_service,
                    single_step=single_step,
                    hash_values_of_files=hash_values_of_files,
                )
                if is_executed:
                    processed_files += 1
                if error:
                    error_raised += 1
            except StopExecution as exception:
                execution_service.update_execution(
                    ExecutionStatus.STOPPED, error=str(exception)
                )
                break
        if error_raised and error_raised == total_files:
            execution_service.update_execution(ExecutionStatus.ERROR)
        else:
            execution_service.update_execution(ExecutionStatus.COMPLETED)

        execution_service.publish_final_workflow_logs(
            total_files=total_files, processed_files=processed_files
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
        hash_values_of_files: dict[str, str],
    ) -> tuple[bool, Optional[str]]:
        file_history = None
        error = None
        is_executed = False
        file_name, file_hash = source.add_file_to_volume(
            input_file_path=input_file,
            hash_values_of_files=hash_values_of_files,
        )
        try:
            execution_service.initiate_tool_execution(
                current_file_idx, total_files, file_name, single_step
            )
            file_history = FileHistoryHelper.get_file_history(
                workflow=workflow, cache_key=file_hash
            )
            is_executed = execution_service.execute_input_file(
                file_name=file_name,
                single_step=single_step,
                file_history=file_history,
            )
        except StopExecution:
            raise
        except Exception as e:
            execution_service.publish_log(
                f"'Error processing file '{os.path.basename(input_file)}'. {str(e)}",
                level=LogLevel.ERROR,
            )
            error = str(e)
        execution_service.publish_update_log(
            LogState.RUNNING,
            f"Processing output for {file_name}",
            LogComponent.DESTINATION,
        )
        destination.handle_output(
            file_name=file_name,
            file_hash=file_hash,
            workflow=workflow,
            file_history=file_history,
            error=error,
            input_file_path=input_file,
        )
        execution_service.publish_update_log(
            LogState.SUCCESS,
            f"{file_name}'s output is processed successfully",
            LogComponent.DESTINATION,
        )
        return is_executed, error

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
        hash_values_of_files: dict[str, str] = {},
        organization_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        scheduled: bool = False,
        single_step: bool = False,
        workflow_execution: Optional[WorkflowExecution] = None,
        execution_mode: Optional[tuple[str, str]] = None,
        include_metadata: bool = False,
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
            include_metadata=include_metadata,
        )
        execution_id = execution_service.execution_id
        source = SourceConnector(
            organization_id=organization_id,
            workflow=workflow,
            execution_id=execution_id,
            execution_service=execution_service,
        )
        destination = DestinationConnector(workflow=workflow, execution_id=execution_id)
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
            # TODO: Update through signals
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
                        pipeline_id, Pipeline.PipelineStatus.SUCCESS
                    )
                else:
                    PipelineProcessor.update_pipeline(
                        pipeline_id, Pipeline.PipelineStatus.FAILURE
                    )
        # Expected exception since API deployments are not tracked in Pipeline
        except Pipeline.DoesNotExist:
            pass
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
            task.status,
            result=task.result,
        )

    @staticmethod
    def execute_workflow_async(
        workflow_id: str,
        execution_id: str,
        hash_values_of_files: dict[str, str],
        timeout: int = -1,
        pipeline_id: Optional[str] = None,
        include_metadata: bool = False,
    ) -> ExecutionResponse:
        """Adding a workflow to the queue for execution.

        Args:
            workflow_id (str): workflowId
            execution_id (str): Execution ID
            timeout (int):  Celery timeout (timeout -1 : async execution)
            pipeline_id (Optional[str], optional): Optional pipeline. Defaults to None.
            include_metadata (bool): Whether to include metadata in the prompt output

        Returns:
            ExecutionResponse: Existing status of execution
        """
        try:
            org_schema = UserContext.get_organization_identifier()
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            async_execution = WorkflowHelper.execute_bin.delay(
                org_schema,
                workflow_id,
                hash_values_of_files=hash_values_of_files,
                execution_id=execution_id,
                pipeline_id=pipeline_id,
                log_events_id=log_events_id,
                include_metadata=include_metadata,
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
            return ExecutionResponse(
                workflow_id,
                execution_id,
                task.status,
                result=task_result,
            )
        except celery_exceptions.TimeoutError:
            return ExecutionResponse(
                workflow_id,
                execution_id,
                async_execution.status,
                message=WorkflowMessages.CELERY_TIMEOUT_MESSAGE,
            )
        except Exception as error:
            WorkflowExecutionServiceHelper.update_execution_status(
                execution_id, ExecutionStatus.ERROR
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
        hash_values_of_files: dict[str, str],
        scheduled: bool = False,
        execution_mode: Optional[tuple[str, str]] = None,
        pipeline_id: Optional[str] = None,
        include_metadata: bool = False,
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
            include_metadata (bool): Whether to include metadata in the prompt output

        Kwargs:
            log_events_id (str): Session ID of the user,
                helps establish WS connection for streaming logs to the FE

        Returns:
            dict[str, list[Any]]: Returns a dict with result from workflow execution
        """
        task_id = current_task.request.id
        # Set organization in state store for execution
        StateStore.set(Account.ORGANIZATION_ID, schema_name)
        return WorkflowHelper.execute_workflow(
            organization_id=schema_name,
            task_id=task_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            hash_values_of_files=hash_values_of_files,
            scheduled=scheduled,
            execution_mode=execution_mode,
            pipeline_id=pipeline_id,
            include_metadata=include_metadata,
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
        execution_mode: Optional[tuple[str, str]] = None,
        pipeline_id: Optional[str] = None,
        include_metadata: bool = False,
        **kwargs: dict[str, Any],
    ) -> Optional[list[Any]]:
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
            include_metadata (bool): Whether to include metadata in the prompt output

        Kwargs:
            log_events_id (str): Session ID of the user, helps establish
                WS connection for streaming logs to the FE

        Returns:
            dict[str, list[Any]]: Returns a dict with result from
                workflow execution
        """
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
        result = WorkflowHelper.run_workflow(
            workflow=workflow,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            scheduled=scheduled,
            workflow_execution=workflow_execution,
            execution_mode=execution_mode,
            hash_values_of_files=hash_values_of_files,
            include_metadata=include_metadata,
        ).result
        return result

    @staticmethod
    def complete_execution(
        workflow: Workflow,
        execution_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        hash_values_of_files: dict[str, str] = {},
        include_metadata: bool = False,
    ) -> ExecutionResponse:
        if pipeline_id:
            logger.info(f"Executing pipeline: {pipeline_id}")
            response: ExecutionResponse = WorkflowHelper.execute_workflow_async(
                workflow_id=workflow.id,
                pipeline_id=pipeline_id,
                execution_id=str(uuid.uuid4()),
                hash_values_of_files=hash_values_of_files,
            )
            return response
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
                include_metadata=include_metadata,
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
        hash_values_of_files: dict[str, str] = {},
        include_metadata: bool = False,
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
                    include_metadata=include_metadata,
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
