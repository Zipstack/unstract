from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models import WorkflowExecution

from tags.models import Tag


class TagHelper:
    @staticmethod
    def list_workflow_executions(tag: Tag):
        """Lists all workflow executions that are tagged with the given tag.

        Args:
            tag (str): The tag to filter workflow executions by.

        Returns:
            QuerySet: A QuerySet containing the filtered WorkflowExecution objects.
        """
        return WorkflowExecution.objects.filter(tags=tag)

    @staticmethod
    def list_workflow_file_executions(tag: Tag):
        """Lists all workflow file executions that are tagged with the given tag.

        Args:
            tag (str): The tag to filter workflow file executions by.

        Returns:
            QuerySet: A QuerySet containing the filtered WorkflowFileExecution objects.
        """
        return WorkflowFileExecution.objects.filter(workflow_execution__tags=tag)
