from dataclasses import dataclass
from typing import Any


@dataclass
class LogLineDTO:
    is_terminated: bool = False  # True if the tool log has termination marker
    with_result: bool = False  # True if the tool log contains a result
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_terminated": self.is_terminated,
            "with_result": self.with_result,
            "error": self.error,
        }
