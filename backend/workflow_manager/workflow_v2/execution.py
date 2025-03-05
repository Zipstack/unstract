import logging
import time
from typing import Optional

from account_v2.constants import Common
from django.utils import timezone
from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
from tags.models import Tag
from tool_instance_v2.models import ToolInstance
from tool_instance_v2.tool_processor import ToolProcessor
from unstract.tool_registry.dto import Tool
from unstract.workflow_execution import WorkflowExecutionService
from unstract.workflow_execution.dto import ToolInstance as ToolInstanceDataClass
from unstract.workflow_execution.dto import WorkflowDto
from unstract.workflow_execution.enums import ExecutionType, LogComponent, LogState
from unstract.workflow_execution.exceptions import StopExecution
from usage_v2.helper import UsageHelper
from utils.local_context import StateStore
from utils.user_context import UserContext
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.exceptions import WorkflowExecutionError
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution
from workflow_manager.workflow_v2.models.execution import EXECUTION_ERROR_LENGTH

logger = logging.getLogger(__name__)


class WorkflowExecutionServiceHelper(WorkflowExecutionService):
    def __init__(
        self,
        workflow: Workflow,
        tool_instances: list[ToolInstance],
        organization_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        single_step: bool = False,
        scheduled: bool = False,
        mode: tuple[str, str] = WorkflowExecution.Mode.INSTANT,
        workflow_execution: Optional[WorkflowExecution] = None,
        use_file_history: bool = True,
    ) -> None:
        tool_instances_as_dto = []
        for tool_instance in tool_instances:
            tool_instances_as_dto.append(
                self.convert_tool_instance_model_to_data_class(tool_instance)
            )
        workflow_as_dto: WorkflowDto = self.convert_workflow_model_to_data_class(
            workflow=workflow
        )
        organization_id = organization_id or UserContext.get_organization_identifier()
        if not organization_id:
            raise WorkflowExecutionError(detail="invalid Organization ID")

        platform_key = PlatformAuthenticationService.get_active_platform_key()
        super().__init__(
            organization_id=organization_id,
            workflow_id=workflow.id,
            workflow=workflow_as_dto,
            tool_instances=tool_instances_as_dto,
            platform_service_api_key=str(platform_key.key),
            ignore_processed_entities=False,
        )
        if not workflow_execution:
            # Use pipline_id for pipelines / API deployment
            # since session might not be present.
            log_events_id = StateStore.get(Common.LOG_EVENTS_ID)
            self.execution_log_id = log_events_id if log_events_id else pipeline_id
            self.execution_mode = mode
            self.execution_method: tuple[str, str] = (
                WorkflowExecution.Method.SCHEDULED
                if scheduled
                else WorkflowExecution.Method.DIRECT
            )
            self.execution_type: tuple[str, str] = (
                WorkflowExecution.Type.STEP
                if single_step
                else WorkflowExecution.Type.COMPLETE
            )
            workflow_execution = WorkflowExecution(
                pipeline_id=pipeline_id,
                workflow_id=workflow.id,
                execution_mode=mode,
                execution_method=self.execution_method,
                execution_type=self.execution_type,
                status=ExecutionStatus.INITIATED,
                execution_log_id=self.execution_log_id,
            )
            workflow_execution.save()
        else:
            self.workflow_execution = workflow_execution
            self.execution_mode = workflow_execution.execution_mode
            self.execution_method = workflow_execution.execution_method
            self.execution_type = workflow_execution.execution_type
            self.execution_log_id = workflow_execution.execution_log_id

        self.set_messaging_channel(str(self.execution_log_id))
        project_settings = {}
        project_settings[WorkflowKey.WF_PROJECT_GUID] = str(self.execution_log_id)
        self.workflow_id = workflow.id
        self.project_settings = project_settings
        self.pipeline_id = pipeline_id
        self.execution_id = str(workflow_execution.id)
        self.use_file_history = use_file_history
        self.tags = workflow_execution.tag_names
        logger.info(
            f"Executing for Pipeline ID: {pipeline_id}, "
            f"workflow ID: {self.workflow_id}, execution ID: {self.execution_id}, "
            f"web socket messaging channel ID: {self.execution_log_id}"
        )

        self.compilation_result = self.compile_workflow(execution_id=self.execution_id)

    @classmethod
    def create_workflow_execution(
        cls,
        workflow_id: str,
        pipeline_id: Optional[str] = None,
        single_step: bool = False,
        scheduled: bool = False,
        log_events_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        mode: tuple[str, str] = WorkflowExecution.Mode.INSTANT,
        tags: Optional[list[Tag]] = None,
        total_files: int = 0,
    ) -> WorkflowExecution:
        # Validating with existing execution
        existing_execution = cls.get_execution_instance_by_id(execution_id)
        if existing_execution:
            return existing_execution

        execution_method: tuple[str, str] = (
            WorkflowExecution.Method.SCHEDULED
            if scheduled
            else WorkflowExecution.Method.DIRECT
        )
        execution_type: tuple[str, str] = (
            WorkflowExecution.Type.STEP
            if single_step
            else WorkflowExecution.Type.COMPLETE
        )
        execution_log_id = log_events_id if log_events_id else pipeline_id
        # TODO: Using objects.create() instead
        workflow_execution = WorkflowExecution(
            pipeline_id=pipeline_id,
            workflow_id=workflow_id,
            execution_mode=mode,
            execution_method=execution_method,
            execution_type=execution_type,
            status=ExecutionStatus.PENDING,
            execution_log_id=execution_log_id,
            total_files=total_files,
        )
        if execution_id:
            workflow_execution.id = execution_id
        workflow_execution.save()
        if tags:
            workflow_execution.tags.set(tags)
        return workflow_execution

    def update_execution(
        self,
        status: Optional[ExecutionStatus] = None,
        error: Optional[str] = None,
        increment_attempt: bool = False,
    ) -> None:
        execution = WorkflowExecution.objects.get(pk=self.execution_id)

        if status is not None:
            execution.status = status.value

            if (
                status
                in [
                    ExecutionStatus.COMPLETED,
                    ExecutionStatus.ERROR,
                    ExecutionStatus.STOPPED,
                ]
                and not execution.execution_time
            ):
                execution.execution_time = round(
                    (timezone.now() - execution.created_at).total_seconds(), 3
                )
        if error:
            execution.error_message = error[:EXECUTION_ERROR_LENGTH]
        if increment_attempt:
            execution.attempts += 1

        execution.save()

    def has_successful_compilation(self) -> bool:
        return self.compilation_result["success"] is True

    def get_execution_instance(self) -> WorkflowExecution:
        execution: WorkflowExecution = WorkflowExecution.objects.get(
            pk=self.execution_id
        )
        return execution

    @classmethod
    def get_execution_instance_by_id(
        cls, execution_id: str
    ) -> Optional[WorkflowExecution]:
        """Get execution by execution ID.

        Args:
            execution_id (str): UID of execution entity

        Returns:
            Optional[WorkflowExecution]: WorkflowExecution Entity
        """
        try:
            execution: WorkflowExecution = WorkflowExecution.objects.get(
                pk=execution_id
            )
            return execution
        except WorkflowExecution.DoesNotExist:
            return None

    def build(self) -> None:
        if self.compilation_result["success"] is True:
            self.build_workflow()
            self.update_execution(status=ExecutionStatus.READY)
        else:
            logger.error(
                "Errors while compiling workflow "
                f"{self.compilation_result['problems']}"
            )
            self.update_execution(
                status=ExecutionStatus.ERROR,
                error=self.compilation_result["problems"][0],
            )
            raise WorkflowExecutionError(self.compilation_result["problems"][0])

    def execute(self, file_execution_id: str, single_step: bool = False) -> None:
        execution_type = ExecutionType.COMPLETE
        if single_step:
            execution_type = ExecutionType.STEP

        if self.compilation_result["success"] is False:
            error_message = (
                f"Errors while compiling workflow "
                f"{self.compilation_result['problems'][0]}"
            )
            raise WorkflowExecutionError(error_message)

        if self.execution_mode not in (
            WorkflowExecution.Mode.INSTANT,
            WorkflowExecution.Mode.QUEUE,
        ):
            error_message = f"Unknown Execution Method {self.execution_mode}"
            raise WorkflowExecutionError(error_message)

        start_time = time.time()
        try:
            self.execute_workflow(
                file_execution_id=file_execution_id,
                execution_type=execution_type,
            )
            end_time = time.time()
            execution_time = end_time - start_time
        except StopExecution as exception:
            end_time = time.time()
            execution_time = end_time - start_time
            logger.info(f"Execution {self.execution_id} stopped")
            raise exception
        except Exception as exception:
            end_time = time.time()
            execution_time = end_time - start_time
            message = str(exception)[:EXECUTION_ERROR_LENGTH]
            logger.error(
                f"Execution {self.execution_id} ran for {execution_time:.4f}s, "
                f" Error {exception}"
            )
            raise WorkflowExecutionError(message) from exception

    def publish_initial_workflow_logs(self, total_files: int) -> None:
        """Publishes the initial logs for the workflow.

        Args:
            total_files (int): The total number of matched files.

        Returns:
            None
        """
        self.publish_log(f"Total matched files: {total_files}")
        self.publish_update_log(LogState.BEGIN_WORKFLOW, "1", LogComponent.STATUS_BAR)
        self.publish_update_log(
            LogState.RUNNING, "Ready for execution", LogComponent.WORKFLOW
        )

    def publish_final_workflow_logs(
        self, total_files: int, successful_files: int, failed_files: int
    ) -> None:
        """Publishes the final logs for the workflow.

        Returns:
            None
        """
        self.publish_update_log(LogState.END_WORKFLOW, "1", LogComponent.STATUS_BAR)
        self.publish_update_log(
            LogState.SUCCESS, "Executed successfully", LogComponent.WORKFLOW
        )
        self.publish_log(
            f"Total files: {total_files}, "
            f"{successful_files} successfully executed and {failed_files} error(s)"
        )

    def publish_average_cost_log(self, execution_id, total_files):

        total_cost = round(UsageHelper.get_aggregated_cost(execution_id), 5)
        average_cost = total_cost/total_files
        self.publish_log(      
            message=f"The average cost per file for execution {execution_id} is {average_cost}"
        )

    def log_total_cost_per_file(self, run_id, file_name):
        cost_dict = UsageHelper.get_aggregated_token_count(run_id=run_id)        
        cost = round(cost_dict.get("cost_in_dollars", 0), 5)

        # Log the total cost for a particular file executed in the workflow
        self.publish_log(
            message=f"Total cost for file {file_name} is ${cost}"
        )

    def publish_initial_tool_execution_logs(
        self, current_file_idx: int, total_files: int, file_name: str
    ) -> None:
        """Publishes the initial logs for tool execution.

        Args:
            current_file_idx (int): 1-based index for the current file being processed
            total_files (int): The total number of files to process
            file_name (str): The name of the file being processed.

        Returns:
            None
        """
        self.publish_update_log(
            component=LogComponent.STATUS_BAR,
            state=LogState.MESSAGE,
            message=f"Processing file {file_name} {current_file_idx}/{total_files}",
        )
        self.publish_log(f"Processing file {file_name}")

    def execute_input_file(
        self,
        file_execution_id: str,
        file_name: str,
        single_step: bool,
        workflow_file_execution: WorkflowFileExecution,
    ) -> None:
        """Executes the input file.

        Args:
            file_execution_id (str): UUID for a single run of a file
            file_name (str): The name of the file to be executed.
            single_step (bool): Flag indicating whether to execute in
            single step mode.
        """
        execution_type = ExecutionType.COMPLETE
        if single_step:
            execution_type = ExecutionType.STEP
        self.publish_log(
            f"No entries found in cache, executing the tool for '{file_name}'"
        )
        self.publish_update_log(
            state=LogState.SUCCESS,
            message=f"{file_name} Sent for execution",
            component=LogComponent.SOURCE,
        )
        workflow_file_execution.update_status(ExecutionStatus.EXECUTING)

        logger.info(
            f"Running execution: '{self.execution_id}',  "
            f"file_execution_id: '{file_execution_id}', "
            f"file '{file_name}'"
        )

        self.execute(file_execution_id, single_step)
        self.publish_log(f"Tool executed successfully for '{file_name}'")
        self._handle_execution_type(execution_type)

    def initiate_tool_execution(
        self,
        current_file_idx: int,
        total_files: int,
        file_name: str,
        single_step: bool,
    ) -> None:
        """Initiates the execution of a tool for a specific file in the
        workflow.

        Args:
            current_file_idx (int): 1-based index for the current file being processed
            total_step (int): The total number of files to process in the workflow
            file_name (str): The name of the file being processed
            single_step (bool): Flag indicating whether the execution is in
            single-step mode

        Returns:
            None

        Raises:
        None
        """
        execution_type = ExecutionType.COMPLETE
        if single_step:
            execution_type = ExecutionType.STEP
        self.publish_initial_tool_execution_logs(
            current_file_idx, total_files, file_name
        )
        self._handle_execution_type(execution_type)

        source_status_message = (
            f"({current_file_idx}/{total_files})Processing file {file_name}"
        )
        self.publish_update_log(
            state=LogState.RUNNING,
            message=source_status_message,
            component=LogComponent.SOURCE,
        )
        self.publish_log("Trying to fetch results from cache")

    @staticmethod
    def update_execution_err(execution_id: str, err_msg: str = "") -> WorkflowExecution:
        try:
            execution = WorkflowExecution.objects.get(pk=execution_id)
            execution.status = ExecutionStatus.ERROR
            execution.error_message = err_msg[:EXECUTION_ERROR_LENGTH]
            execution.save()
            return execution
        except WorkflowExecution.DoesNotExist:
            logger.error(f"execution doesn't exist {execution_id}")

    @staticmethod
    def update_execution_task(execution_id: str, task_id: str) -> None:
        try:
            if not task_id:
                logger.warning(
                    f"task_id: '{task_id}' is NULL / empty for "
                    f"execution_id: {execution_id}, expected to have a UUID"
                )
            execution = WorkflowExecution.objects.get(pk=execution_id)
            # TODO: Review if status should be updated to EXECUTING
            execution.task_id = task_id
            execution.save()
        except WorkflowExecution.DoesNotExist:
            logger.error(f"execution doesn't exist {execution_id}")

    @staticmethod
    def convert_tool_instance_model_to_data_class(
        tool_instance: ToolInstance,
    ) -> ToolInstanceDataClass:
        tool: Tool = ToolProcessor.get_tool_by_uid(tool_instance.tool_id)
        tool_dto = ToolInstanceDataClass(
            id=tool_instance.id,
            tool_id=tool_instance.tool_id,
            workflow=tool_instance.workflow.id,
            metadata=tool_instance.metadata,
            step=tool_instance.step,
            properties=tool.properties,
            image_name=tool.image_name,
            image_tag=tool.image_tag,
        )
        return tool_dto

    @staticmethod
    def convert_workflow_model_to_data_class(
        workflow: Workflow,
    ) -> WorkflowDto:
        return WorkflowDto(id=workflow.id)
