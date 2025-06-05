from dataclasses import dataclass
from enum import Enum
from typing import Any


class RunnerContainerRunStatus(Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    RUNNING = "RUNNING"


@dataclass
class RunnerContainerRunResponse:
    type: str
    result: dict[str, Any] | None
    error: str | None
    status: RunnerContainerRunStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "result": self.result,
            "error": self.error,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunnerContainerRunResponse":
        return cls(
            type=data.get("type"),
            result=data.get("result"),
            error=data.get("error"),
            status=RunnerContainerRunStatus(data.get("status")),
        )


@dataclass
class RunnerContainerRunStatusResponse:
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
        }
