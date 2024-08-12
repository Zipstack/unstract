from typing import Any, Optional


class PipelineStatusPayload:
    def __init__(
        self,
        type: str,
        pipeline_id: str,
        pipeline_name: str,
        status: str,
        execution_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        self.type = type
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.status = status
        self.execution_id = execution_id
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Convert the payload DTO to a dictionary."""
        payload = {
            "type": self.type,
            "pipeline_id": str(self.pipeline_id),
            "pipeline_name": self.pipeline_name,
            "status": self.status,
        }
        if self.execution_id:
            payload["execution_id"] = str(self.execution_id)
        if self.error_message:
            payload["error_message"] = self.error_message
        return payload
