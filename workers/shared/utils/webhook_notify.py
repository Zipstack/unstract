"""Webhook delivery for terminal Agent-KV job callbacks (spec §5.3/§5.4).

STUB — Task 13 replaces this module with the real implementation (HTTP
delivery, retries, HTTPS enforcement via ``allow_http``, auth headers).
It exists now only so ``ide_callback/agent_kv_tasks.py`` has a stable
import target during Task 12; ``send_webhook`` always returns ``False``
(no delivery attempted) until Task 13 lands. Callers must not treat a
``False`` return as a delivery failure worth retrying/alerting on until
then.
"""

from typing import Any


def send_webhook(url: str, payload: dict[str, Any], *, allow_http: bool = False) -> bool:
    """Placeholder webhook sender.

    Args:
        url: Destination webhook URL.
        payload: JSON-serializable body to deliver.
        allow_http: Whether to permit a plain ``http://`` URL (Task 13 will
            enforce HTTPS unless this is set).

    Returns:
        Always ``False`` in this stub. Task 13 replaces this with a real
        HTTP POST that returns whether delivery succeeded.
    """
    return False
