from typing import Any

from workflow_manager.endpoint.dto import FileHash
from workflow_manager.workflow.models.workflow import Workflow


class WorkflowUtil:

    @staticmethod
    def _mrq_files(
        percentage: float,
        n: int,
    ) -> Any:
        pass

    @classmethod
    def get_q_no_list(cls, workflow: Workflow, total_files: int) -> Any:
        pass

    @staticmethod
    def add_file_destination_filehash(
        index: int,
        q_file_no_list: Any,
        file_hash: FileHash,
    ) -> FileHash:
        return file_hash
