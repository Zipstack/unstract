import logging

from api_v2.utils import APIDeploymentUtils
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

logger = logging.getLogger(__name__)


class PipelineUtils:
    """Utility class for pipeline-workflow related operations."""

    @staticmethod
    def update_pipeline_status(
        pipeline_id: str | None, workflow_execution: WorkflowExecution
    ) -> None:
        """Updates the pipeline status based on the workflow execution status.

        Args:
            pipeline_id (str | None): The ID of the pipeline to update.
            workflow_execution (WorkflowExecution): The workflow execution object.
        """
        try:
            if pipeline_id:
                # Update pipeline status
                if workflow_execution.status == ExecutionStatus.COMPLETED.value:
                    PipelineProcessor.update_pipeline(
                        pipeline_id,
                        Pipeline.PipelineStatus.SUCCESS,
                        execution_id=workflow_execution.id,
                        is_end=True,
                    )
                elif workflow_execution.status in [
                    ExecutionStatus.ERROR.value,
                    ExecutionStatus.STOPPED.value,
                ]:
                    PipelineProcessor.update_pipeline(
                        pipeline_id,
                        Pipeline.PipelineStatus.FAILURE,
                        execution_id=workflow_execution.id,
                        error_message=workflow_execution.error_message,
                        is_end=True,
                    )
                else:
                    # Update pipeline status for other statuses.Currently this method is
                    # called only for COMPLETED and ERROR statuses.
                    logger.warning(
                        f"Workflow execution {workflow_execution.id} with status {workflow_execution.status}"
                        f"is not handled in update_pipeline_status method."
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
