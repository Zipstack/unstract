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
        is_failure: bool | None = None,
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
        # Authoritative failure verdict computed at dispatch (see
        # is_failure_run + the pipeline last_run_status backstop). Lets the
        # clubbed renderer classify the run without re-deriving it from the
        # `status` string, whose vocabulary differs per dispatch path
        # (PipelineStatus on the pipeline path vs ExecutionStatus elsewhere).
        self.is_failure = is_failure

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
        # Only emit when explicitly set so worker/legacy payloads (which never
        # carry it) stay byte-identical and the renderer falls back to status.
        if self.is_failure is not None:
            payload["is_failure"] = self.is_failure
        return payload
