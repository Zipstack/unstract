from typing import Any

from workflow_manager.workflow_v2.enums import ExecutionStatus

MESSAGE_KEY = "message"


def flatten_error(data: dict[str, Any]) -> str:
    errors = data.get("errors")
    if isinstance(errors, list):
        parts = []
        for err in errors:
            if not isinstance(err, dict):
                parts.append(str(err))
                continue
            detail = str(err.get("detail", ""))
            attr = err.get("attr")
            parts.append(f"{attr}: {detail}" if attr else detail)
        return "; ".join(parts)
    if errors is not None:
        return str(errors)
    return str(data.get("error", ""))


def add_error_message(data: Any) -> Any:
    """Mirror an error body into the `message.error` slot the execution
    responses use, so a client reads one key for every outcome.

    Strictly additive: published clients parse the existing keys, so they are
    left exactly as the exception handler produced them.
    """
    if not isinstance(data, dict) or MESSAGE_KEY in data:
        return data
    data[MESSAGE_KEY] = {
        "execution_status": ExecutionStatus.ERROR.value,
        "error": flatten_error(data),
    }
    return data
