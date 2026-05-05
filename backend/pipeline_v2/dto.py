from typing import Any


class PipelineStatusPayload:
    def __init__(
        self,
        type: str,
        pipeline_id: str,
        pipeline_name: str,
        status: str,
        execution_id: str | None = None,
        error_message: str | None = None,
        total_files: int | None = None,
        successful_files: int | None = None,
        failed_files: int | None = None,
    ):
        self.type = type
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.status = status
        self.execution_id = execution_id
        self.error_message = error_message
        self.total_files = total_files
        self.successful_files = successful_files
        self.failed_files = failed_files

    def to_dict(self) -> dict[str, Any]:
        """Convert the payload DTO to a dictionary.

        File counts are nested in `additional_data` to match the worker-path
        payload shape (NotificationPayload.from_execution_status).
        """
        payload: dict[str, Any] = {
            "type": self.type,
            "pipeline_id": str(self.pipeline_id),
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "additional_data": {
                "total_files": self.total_files or 0,
                "successful_files": self.successful_files or 0,
                "failed_files": self.failed_files or 0,
            },
        }
        if self.execution_id:
            payload["execution_id"] = str(self.execution_id)
        if self.error_message:
            payload["error_message"] = self.error_message
        return payload
