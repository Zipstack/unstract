import logging

from account_v2.constants import Common
from utils.local_context import StateStore

from unstract.core.pubsub_helper import LogPublisher
from unstract.workflow_execution.enums import (
    LogComponent,
    LogLevel,
    LogStage,
    LogState,
)


class WorkflowLog:
    def __init__(
        self,
        execution_id: str,
        log_stage: LogStage,
        file_execution_id: str | None = None,
        organization_id: str | None = None,
        pipeline_id: str | None = None,
    ):
        log_events_id: str | None = StateStore.get(Common.LOG_EVENTS_ID)
        self.messaging_channel = log_events_id if log_events_id else pipeline_id
        self.execution_id = str(execution_id)
        self.file_execution_id = str(file_execution_id) if file_execution_id else None
        self.organization_id = str(organization_id) if organization_id else None
        self.log_stage = log_stage

    def publish_log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        step: int | None = None,
    ) -> None:
        log_details = LogPublisher.log_workflow(
            stage=self.log_stage.value,
            message=message,
            level=level.value,
            step=step,
            execution_id=self.execution_id,
            file_execution_id=self.file_execution_id,
            organization_id=self.organization_id,
        )
        LogPublisher.publish(self.messaging_channel, log_details)

    def log_error(self, logger: logging.Logger, message: str) -> None:
        self.publish_log(message, level=LogLevel.ERROR)
        logger.error(message, exc_info=True, stack_info=True)

    def log_info(self, message: str) -> None:
        self.publish_log(message, level=LogLevel.INFO)

    def publish_update_log(
        self,
        state: LogState,
        message: str,
        component: str | LogComponent | None = None,
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
        self,
        total_files: int,
        successful_files: int,
        failed_files: int,
    ) -> None:
        """Publishes the final logs for the workflow.

        Args:
            total_files (int): The total number of matched files.
            successful_files (int): The number of successfully executed files.
            failed_files (int): The number of failed files.

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

    def publish_average_cost_log(
        self,
        logger: logging.Logger,
        total_files: int,
        execution_id: str,
        total_cost: float,
    ):
        """Publishes the average cost log for the workflow.

        Args:
            logger (logging.Logger): The logger to use for logging.
            total_files (int): The total number of files.
            execution_id (str): The ID of the execution.
            total_cost (float): The total cost of the execution.

        Returns:
            None
        """
        try:
            if total_cost is not None:
                average_cost = round(total_cost / total_files, 5)
                self.publish_log(
                    message=(
                        f"The average cost per file for execution "
                        f"'{execution_id}' is '${average_cost}'"
                    )
                )
        except Exception as e:
            logger.warning(
                f"Unable to get aggregated cost for '{execution_id}': {str(e)}"
            )
