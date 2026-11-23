"""Socket event sent when a Prompt Studio prompt run is dispatched.

A separate event name from ``prompt_studio_result`` (sent by the ide_callback
worker when the run ends), so listeners of that event see no new status.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from utils.log_events import _emit_websocket_event

logger = logging.getLogger(__name__)

PROMPT_STUDIO_RUN_STARTED_EVENT = "prompt_studio_run_started"


def emit_run_started(cb_kwargs: dict[str, Any]) -> None:
    """Tell the client a run was dispatched. Never raises.

    ``cb_kwargs`` is the callback payload of the dispatched task, after
    ``executor_task_id`` and ``dispatch_time`` are set.
    """
    room = cb_kwargs.get("log_events_id")
    if not room:
        return
    dispatch_time = cb_kwargs.get("dispatch_time")
    payload = {
        "task_id": cb_kwargs.get("executor_task_id", ""),
        "operation": cb_kwargs.get("operation", "fetch_response"),
        "tool_id": cb_kwargs.get("tool_id", ""),
        "status": "started",
        "run_id": cb_kwargs.get("run_id", ""),
        "prompt_ids": cb_kwargs.get("prompt_ids", []),
        "document_id": cb_kwargs.get("document_id", ""),
        "profile_manager_id": cb_kwargs.get("profile_manager_id"),
        "started_at": (
            datetime.fromtimestamp(dispatch_time, tz=UTC).isoformat()
            if dispatch_time
            else None
        ),
    }
    try:
        _emit_websocket_event(
            room,
            PROMPT_STUDIO_RUN_STARTED_EVENT,
            json.loads(json.dumps(payload, default=str)),
        )
    except Exception:
        logger.warning(
            "Failed to emit %s", PROMPT_STUDIO_RUN_STARTED_EVENT, exc_info=True
        )
