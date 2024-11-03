from typing import Any

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.workflow_v2.models.workflow import Workflow


class WorkflowUtil:
    """A utility class for managing workflow operations, particularly for
    selecting files for manual review and updating file destination based on
    review criteria."""

    @staticmethod
    def _mrq_files(
        percentage: float,
        n: int,
    ) -> Any:
        """Placeholder method for selecting a subset of files based on a given
        percentage.

        Args:
            percentage (float): The percentage of files to select.
            n (int): The total number of files.

        Returns:
            Any: The method is currently a placeholder and does not return a value.
        """
        pass

    @classmethod
    def get_q_no_list(cls, workflow: Workflow, total_files: int) -> Any:
        """Placeholder method for retrieving a list of files to be reviewed
        based on workflow rules.

        Args:
            workflow (Workflow): The workflow instance to be processed.
            total_files (int): The total number of files in the workflow.

        Returns:
            Any: The method is currently a placeholder and does not return a value.
        """
        pass

    @staticmethod
    def add_file_destination_filehash(
        index: int,
        q_file_no_list: Any,
        file_hash: FileHash,
    ) -> FileHash:
        """Updates the file destination in the FileHash object if the file
        index is marked for manual review.

        Args:
            index (int): The index of the file being processed.
            q_file_no_list (Any): A list or set of file indices marked for review.
            file_hash (FileHash): The FileHash object to be updated.

        Returns:
            FileHash: The potentially updated FileHash object with the file
            destination modified.
        """
        return file_hash
