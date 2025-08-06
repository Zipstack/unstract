from typing import Any

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.workflow_v2.models.workflow import Workflow


class WorkflowUtil:
    """A utility class for managing workflow operations, particularly for
    selecting files for manual review and updating file destination based on
    review criteria.
    """

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

    @staticmethod
    def validate_db_rule(
        result: Any | None,
        workflow_id: Workflow,
        file_destination: tuple[str, str] | None,
    ) -> bool:
        """Placeholder method to check the db rules - MRQ

        Args:
            result (Optional[Any]): The result dictionary containing
            confidence_data.
            workflow_id (str): The ID of the workflow to retrieve the rules.
            file_destination (Optional[tuple[str, str]]): The destination of
            the file (e.g., MANUALREVIEW or other).

        Returns:
            bool: True if the field_key conditions are met based on rule logic
            and file destination.
        """
        return False

    @staticmethod
    def get_hitl_ttl_seconds(workflow: Workflow) -> Any:
        """Get TTL in seconds for HITL settings for a workflow.

        Args:
            workflow (Workflow): The workflow to get HITL TTL settings for.

        Returns:
            Optional[int]: TTL in seconds if custom TTL is set, None for unlimited TTL.
        """
        raise NotImplementedError("TTL retrieval not yet implemented")
