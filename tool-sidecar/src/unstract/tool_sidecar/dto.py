from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LogLineDTO:
    is_completion: bool = False
    with_result: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_completion": self.is_completion,
            "with_result": self.with_result,
            "error": self.error,
        }
