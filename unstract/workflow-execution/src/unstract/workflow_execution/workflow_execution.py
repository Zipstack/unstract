import logging
import os
import time
from typing import Any, Optional, Union

import redis
from unstract.tool_sandbox import ToolSandbox
from unstract.workflow_execution.constants import StepExecution, ToolExecution
from unstract.workflow_execution.dto import ToolInstance, WorkflowDto
from unstract.workflow_execution.enums import (
    ExecutionAction,
    ExecutionType,
    LogComponent,
    LogLevel,
    LogStage,
    LogState,
)
from unstract.workflow_execution.exceptions import (
    BadRequestException,
    StopExecution,
    ToolOutputNotFoundException,
)
from unstract.workflow_execution.execution_file_handler import ExecutionFileHandler
from unstract.workflow_execution.tools_utils import ToolsUtils

from unstract.core.pubsub_helper import LogPublisher

logger = logging.getLogger(__name__)


class WorkflowExecutionService:
    redis_con = redis.Redis(
        host=os.environ.get("REDIS_HOST", "http://127.0.0.1"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_USER"),
        username=os.environ.get("REDIS_PASSWORD"),
    )

    def __init__(
        self,
        organization_id: str,
        workflow_id: str,
        workflow: WorkflowDto,
        tool_instances: list[ToolInstance],
        platform_service_api_key: str,
        ignore_processed_entities: bool = False,
    ) -> None:
        self.organization_id = organization_id
        self.workflow_id = workflow_id

        self.tool_instances = tool_instances
        self.tool_utils = ToolsUtils(
            organization_id=organization_id,
            redis=self.redis_con,
            workflow=workflow,
            platform_service_api_key=platform_service_api_key,
            ignore_processed_entities=False,
        )
        self.tool_sandboxes: list[ToolSandbox] = []
        self.ignore_processed_entities = ignore_processed_entities
        self.override_single_step = False
        self.execution_id: str = ""
        self.messaging_channel: Optional[str] = None
        self.input_files: list[str] = []
        self.log_stage: LogStage = LogStage.COMPILE

    def set_messaging_channel(self, messaging_channel: str) -> None:
        self.messaging_channel = messaging_channel
        self.tool_utils.set_messaging_channel(messaging_channel)

    def compile_workflow(self, execution_id: str) -> dict[str, Any]:
        """Compiling workflow Validating all steps and tool instances.

        Args:
            execution_id (str): execution id

        Returns:
            dict[str, Any]: compilation status
        """
        logger.info(f"Execution {execution_id}: compiling workflow started")
        self.log_stage = LogStage.COMPILE
        log_message = (
            f"Compiling workflow '{self.workflow_id}' "
            f"of {len(self.tool_instances)} steps"
        )
        self.publish_log(log_message)

        try:
            self.execution_id = str(execution_id)
            self.file_handler = ExecutionFileHandler(
                self.workflow_id, self.execution_id, self.organization_id
            )

            logger.info(f"Execution {execution_id}: compilation completed")
            log_message = (
                f"Workflow '{self.workflow_id}' is valid "
                "and is compiled successfully"
            )
            self.publish_log(log_message)

            return {
                "workflow": self.workflow_id,
                "success": True,
            }
        except Exception as error:
            self.publish_log(str(error), LogLevel.ERROR)
            return {
                "workflow": self.workflow_id,
                "problems": [str(error)],
                "success": False,
            }

    def build_workflow(self) -> None:
        """Build Workflow by builtin tool sandboxes."""

        logger.info(f"Execution {self.execution_id}: Build started")
        self.log_stage = LogStage.BUILD
        log_message = (
            f"Building workflow '{self.workflow_id}' "
            f"of {len(self.tool_instances)} steps"
        )
        self.publish_log(log_message)

        try:
            self.tool_sandboxes = self.tool_utils.check_to_build(
                tools=self.tool_instances, execution_id=self.execution_id
            )

            log_message = (
                f"Workflow built successfully. Built tools = "
                f"{len(self.tool_instances)}"
            )
            self.publish_log(log_message)
        except Exception as exception:
            self.publish_log(str(exception), LogLevel.ERROR)
            raise exception

        logger.info(f"Execution {self.execution_id}: Build completed")

    def execute_workflow(self, execution_type: ExecutionType) -> None:
        """Executes the complete workflow by running each tools one by one.
        Returns the result from final tool in a dictionary.

        Args:
            execution_type (ExecutionType): STEP or COMPLETE

        Raises:
            BadRequestException: In case someone tries to execute a workflow
                                 with invalid execution id
            error: If any error happens in any of the tool during execution

        Returns:
            dict: A dictionary containing result from final tool.
                  Eg:- {"result": "RESULT_FROM_FINAL_TOOL"}
        """
        self.log_stage = LogStage.RUN
        self._initialize_execution()
        total_steps = len(self.tool_sandboxes)
        self.total_steps = total_steps
        for step, sandbox in enumerate(self.tool_sandboxes):
            self._execute_step(
                step=step,
                sandbox=sandbox,
            )
        self._finalize_execution(execution_type)

    def _execute_step(
        self,
        step: int,
        sandbox: ToolSandbox,
    ) -> None:
        """Execution of workflow step.

        Args:
            step (int): workflow step
            sandbox (ToolSandbox): instance of tool sandbox
            execution_type (ExecutionType): step or complete
            last_step_output (list[Any]): output of previous step

        Raises:
            error: _description_
        """
        # Offset calculation for human readability:
        # 0 (base step) + 1 (for human readability)
        actual_step = step + ToolExecution.STEP_ADJUSTMENT_OFFSET
        tool_uid = sandbox.get_tool_uid()
        tool_instance_id = sandbox.get_tool_instance_id()
        log_message = f"Executing step {actual_step} with tool {tool_uid}"
        logger.info(f"Execution {self.execution_id}: {log_message}")
        self.publish_log(
            log_message,
            step=actual_step,
            iteration=actual_step,
            iteration_total=self.total_steps,
        )
        try:
            self.publish_update_log(
                state=LogState.RUNNING,
                message="Ready for execution",
                component=tool_instance_id,
            )
            self.tool_utils.run_tool(
                tool_sandbox=sandbox,
            )
            if not self.validate_execution_result(step + 1):
                raise ToolOutputNotFoundException(
                    f"Tool exception raised for tool {tool_uid}, "
                    "check logs for more information"
                )
            log_message = f"Step {actual_step} executed successfully"
            self.publish_update_log(
                state=LogState.SUCCESS,
                message="executed successfully",
                component=tool_instance_id,
            )

            logger.info(log_message)
            self.publish_log(log_message, step=actual_step)

        except Exception as error:
            logger.info(f"Error while running tool {tool_uid}: {str(error)}")
            self.publish_log(str(error), LogLevel.ERROR, step=actual_step)
            self.publish_update_log(
                state=LogState.ERROR,
                message="Failed to execute",
                component=tool_instance_id,
            )
            raise error

    def _handling_step_execution(self) -> None:
        """Handle step execution control during single-stepping mode. This
        function waits for user input to proceed to the next step, continue to
        the end of execution, or stop the execution.

        Raises:
            StopExecution: Raised when the user clicks on the stop button.
                Stops the execution immediately.
            RuntimeError: Raised when the user does not click on the
                next button within a specified time, leading to the
                termination of execution.
        """
        with self.redis_con as red:
            logger.info(
                f"Setting single stepping flag to " f"{ExecutionAction.START.value}"
            )
            red.setex(
                self.execution_id,
                StepExecution.CACHE_EXP_START_SEC,
                ExecutionAction.START.value,
            )
            logger.info("Waiting for user to click on next button")
            self.publish_update_log(
                state=LogState.NEXT,
                message="1",
                component=LogComponent.NEXT_STEP,
            )
            log_message = (
                f"Execution '{self.execution_id}' " "is waiting for user input"
            )
            self.publish_log(log_message)

            wait_for_user = 0
            while wait_for_user < StepExecution.WAIT_FOR_NEXT_TRIGGER:
                execution_value_in_byte = red.get(self.execution_id)
                execution_action = None
                execution_value = None
                if execution_value_in_byte is not None:
                    execution_value = execution_value_in_byte.decode("utf-8")
                if execution_value:
                    execution_action = ExecutionAction(execution_value)
                if execution_action == ExecutionAction.NEXT:
                    log_message = (
                        f"Execution '{self.execution_id}' Executing " "NEXT step"
                    )
                    self.publish_log(log_message)
                    break
                if execution_action == ExecutionAction.CONTINUE:
                    log_message = (
                        f"Execution '{self.execution_id}' "
                        "CONTINUE to the end of execution"
                    )
                    self.publish_log(log_message)
                    self.override_single_step = True
                    break
                if execution_action == ExecutionAction.STOP:
                    log_message = (
                        f"Execution '{self.execution_id}' " "STOPPING execution"
                    )
                    self.publish_log(log_message)
                    raise StopExecution(
                        "User clicked on stop button. Stopping execution"
                    )
                time.sleep(1)
                wait_for_user += 1
            red.delete(self.execution_id)
            if wait_for_user >= StepExecution.WAIT_FOR_NEXT_TRIGGER:
                message = (
                    f"User did not click on next button in "
                    f"{StepExecution.WAIT_FOR_NEXT_TRIGGER}.Stopping execution"
                )
                logger.info(message)
                raise RuntimeError(message)

    def _initialize_execution(self) -> None:
        """Initialize the execution process.

        This function performs the initial setup for the execution process,
        including logging the start of execution, updating the status bar,
        and publishing logs for monitoring.

        Raises:
            BadRequestException: Raised if the execution ID is not found.
        """
        if not self.execution_id:
            raise BadRequestException("Execution Id not found")

    def _finalize_execution(self, execution_type: ExecutionType) -> None:
        """Finalize the execution process.

        Args:
            execution_type (ExecutionType): ExecutionType
        """
        if execution_type == ExecutionType.STEP:
            with self.redis_con as r:
                r.delete(self.execution_id)

        log_message = f"Executing workflow {self.workflow_id} Done."
        self.publish_log(log_message)

    def _handle_execution_type(self, execution_type: ExecutionType) -> None:
        """Handling execution type Handling STEP and COMPLETE execution type.

        Args:
            execution_type (ExecutionType): ExecutionType
        """
        if execution_type == ExecutionType.STEP and not self.override_single_step:
            self._handling_step_execution()

    def validate_execution_result(self, step: int) -> bool:
        workflow_metadata = self.file_handler.get_workflow_metadata()
        metadata_list = self.file_handler.get_list_of_tool_metadata(workflow_metadata)
        if len(metadata_list) == step:
            return True
        return False

    def publish_log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        step: Optional[int] = None,
        iteration: Optional[int] = None,
        iteration_total: Optional[int] = None,
    ) -> None:
        """Publishes regular logs for monitoring the execution of a workflow.

        Args:
            state (LogState): The state of the log, such as "RUN" or "COMPILE".
            message (str): The log message to be published.
            level (LogLevel, optional): The log level, such as "INFO"
            or "ERROR". Defaults to "INFO".
            step (int, optional): The step number of the workflow.
            Defaults to None.
            iteration (int, optional): The iteration number of the step.
            Defaults to None.
            iteration_total (int, optional):
            The total number of iterations for the step. Defaults to None.

        Returns:
            None
        """
        log_details = LogPublisher.log_workflow(
            self.log_stage.value,
            message,
            level.value,
            step=step,
            iteration=iteration,
            iteration_total=iteration_total,
            execution_id=self.execution_id,
            organization_id=self.organization_id,
        )
        LogPublisher.publish(self.messaging_channel, log_details)

    def publish_update_log(
        self,
        state: LogState,
        message: str,
        component: Optional[Union[str, LogComponent]] = None,
    ) -> None:
        """Publishes update logs for monitoring the execution of a workflow.

        Args:
            state (LogState): The state of the log, such as "RUN" or "COMPILE".
            message (str): The log message to be published.
            component (LogComponent, optional): The component associated
            with the log. Defaults to None.

        Returns:
            None
        """
        if isinstance(component, LogComponent):
            component = component.value

        log_details = LogPublisher.log_workflow_update(state.value, message, component)
        LogPublisher.publish(self.messaging_channel, log_details)
