"""Extra fields for the ``prompt_studio_result`` events of a prompt run.

``outputs``: the rows the backend persisted for this run, in the shape
``GET prompt-output/`` returns, or ``None`` when they are unavailable or too
large to send (the client then refetches).

``error_details``: provider, request id and retry hint from the executor's
failure metadata. Always the three keys, ``None`` when unknown. Only a failure
the legacy executor caught and returned as a failed result can carry values;
a crashed executor task (``ide_prompt_error``) and a failing callback always
send all three as ``None``.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# The event is POSTed to the backend's emit-websocket view, which is bound by
# Django's 2.5 MB DATA_UPLOAD_MAX_MEMORY_SIZE. Stay well under it.
MAX_INLINE_OUTPUTS_BYTES = 1024 * 1024


def inline_outputs(response: Any) -> list[Any] | None:
    """Rows from the ``update_prompt_output`` response, or ``None``."""
    if not isinstance(response, dict) or not response.get("success"):
        return None
    rows = response.get("data")
    if not isinstance(rows, list):
        return None
    size = len(json.dumps(rows, default=str).encode("utf-8"))
    if size > MAX_INLINE_OUTPUTS_BYTES:
        logger.info(
            "Prompt outputs are %d bytes, over the %d byte inline limit; "
            "sending the event without them",
            size,
            MAX_INLINE_OUTPUTS_BYTES,
        )
        return None
    return rows


def error_details(metadata: Any = None) -> dict[str, Any]:
    """Known keys of ``metadata['error_details']``, type-checked."""
    raw = metadata.get("error_details") if isinstance(metadata, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    retry_after = raw.get("retry_after_seconds")
    return {
        "provider": _str_or_none(raw.get("provider")),
        "request_id": _str_or_none(raw.get("request_id")),
        "retry_after_seconds": (
            retry_after
            if isinstance(retry_after, int) and not isinstance(retry_after, bool)
            else None
        ),
    }


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
