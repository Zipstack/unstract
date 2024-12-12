from typing import Optional

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


class FileExecutionHelper:
    """
    Helper class for handling operations related to `WorkflowExecutionFile` model.
    """

    @staticmethod
    def get_or_create_file_execution(
        workflow_execution: WorkflowExecution,
        file_name: str,
        file_size: int,
        file_hash: str,
        file_path: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> WorkflowFileExecution:
        """
        Retrieves or creates a new input file record for a workflow execution.

        Args:
        workflow_execution: The `WorkflowExecution` object associated with this file
        file_name: The name of the input file
        file_size: The size of the file in bytes
        file_hash: The hash of the file content
        file_path: (Optional) The full path of the input file
        mime_type: (Optional) MIME type of the file

        return:
            The `WorkflowExecutionInputFile` object
        """
        execution_file, is_created = WorkflowFileExecution.objects.get_or_create(
            workflow_execution=workflow_execution,
            file_hash=file_hash,
            file_path=file_path,
        )
        if is_created:
            execution_file.file_name = file_name
            execution_file.file_size = file_size
            execution_file.mime_type = mime_type
            execution_file.save()
        return execution_file

    @staticmethod
    def update_status(
        execution_file: WorkflowFileExecution,
        status: ExecutionStatus,
        execution_time: int = 0,
        execution_error: str = None,
    ) -> WorkflowFileExecution:
        """
        Updates the status and execution details of an input file.

        Args:
        execution_file: The `WorkflowExecutionFile` object to update
        status: The new status of the file
        execution_time: The execution time for processing the file
        execution_error: (Optional) Error message if processing failed

        return:
            The updated `WorkflowExecutionInputFile` object
        """
        execution_file.status = status
        execution_file.execution_time = execution_time
        execution_file.execution_error = execution_error
        execution_file.save()
        return execution_file

    @staticmethod
    def update_execution_error(
        execution_file: WorkflowFileExecution, error_message: str
    ) -> None:
        """
        Updates the execution error for a file in case of failure.

        Args:
        execution_file: The `WorkflowExecutionFile` object to update
        error_message: The error message to set

        return:
            None
        """
        execution_file.execution_error = error_message
        execution_file.status = ExecutionStatus.ERROR
        execution_file.save()
