"""Manual Review Response Classes.

Consistent response formats for manual review operations. Extends the
base response system for consistency.
"""

from dataclasses import dataclass
from typing import Any

from .response_models import APIResponse


@dataclass
class ManualReviewResponse(APIResponse):
    """Consistent response format for manual review operations.

    Extends APIResponse to maintain consistency with the overall
    response system.
    """

    @classmethod
    def success_response(
        cls, data: dict[str, Any], message: str | None = None, status_code: int = 200
    ) -> "ManualReviewResponse":
        """Create a successful manual review response."""
        return cls(success=True, data=data, message=message, status_code=status_code)

    @classmethod
    def error_response(
        cls, error: str, message: str | None = None, status_code: int = 400
    ) -> "ManualReviewResponse":
        """Create an error manual review response."""
        return cls(success=False, error=error, message=message, status_code=status_code)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        result = {
            "success": self.success,
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error is not None:
            result["error"] = self.error

        if self.message is not None:
            result["message"] = self.message

        if self.status_code is not None:
            result["status_code"] = self.status_code

        return result
