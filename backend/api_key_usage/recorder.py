"""Count a key's use when it authenticates a request, without a database write.

Each use is two to four Redis commands in one round trip. The counts wait in
the ``PENDING_*`` hashes until ``flush.flush_pending_usage`` moves them to the
database. Recording also triggers that flush, at most once per
``API_KEY_USAGE_FLUSH_INTERVAL_SECONDS`` across every process, and runs it in a
background thread so the request that triggers it does not wait.

Hash fields, joined by ``FIELD_SEPARATOR``:

* ``PENDING_CALLS``: ``key_type|key_id|organization_id|day`` -> call count
* ``PENDING_LAST_USED``: ``key_type|key_id|organization_id`` -> epoch seconds
* ``PENDING_CALLERS``: ``key_type|key_id|organization_id|api_deployment_id|day``
  -> call count
* ``PENDING_CALLER_LAST``: same field as ``PENDING_CALLERS`` -> epoch seconds
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_redis import get_redis_connection

from api_key_usage.constants import (
    FIELD_SEPARATOR,
    FLUSH_DUE_KEY,
    PENDING_CALLER_LAST,
    PENDING_CALLERS,
    PENDING_CALLS,
    PENDING_LAST_USED,
)

logger = logging.getLogger(__name__)


def join_field(*parts: Any) -> str:
    return FIELD_SEPARATOR.join(str(part) for part in parts)


def record_key_use(
    *,
    key_type: str,
    key_id: Any,
    organization_id: Any,
    api_deployment_id: Any = None,
    at: datetime | None = None,
) -> None:
    """Count one authenticated request for a key. Never raises.

    Call it after the key is accepted. ``organization_id`` is the key's
    ``Organization`` primary key. Pass ``api_deployment_id`` when the key
    authenticated an API deployment, so the key's callers can be listed.
    A Redis failure loses this one count and is logged; the request goes on.
    """
    try:
        at = at or timezone.now()
        day = at.astimezone(UTC).date().isoformat()
        seen = at.timestamp()
        key = join_field(key_type, key_id, organization_id)

        pipe = get_redis_connection("default").pipeline(transaction=False)
        pipe.hincrby(PENDING_CALLS, join_field(key, day), 1)
        pipe.hset(PENDING_LAST_USED, key, seen)
        if api_deployment_id:
            caller = join_field(key, api_deployment_id, day)
            pipe.hincrby(PENDING_CALLERS, caller, 1)
            pipe.hset(PENDING_CALLER_LAST, caller, seen)
        pipe.set(
            FLUSH_DUE_KEY,
            1,
            nx=True,
            ex=settings.API_KEY_USAGE_FLUSH_INTERVAL_SECONDS,
        )
        flush_due = pipe.execute()[-1]
    except Exception:
        logger.exception("Could not record use of %s key %s", key_type, key_id)
        return

    if flush_due:
        start_background_flush()


def start_background_flush() -> None:
    """Run a flush in a daemon thread. Tests replace this to flush inline."""
    threading.Thread(
        target=_flush_and_close, name="api-key-usage-flush", daemon=True
    ).start()


def _flush_and_close() -> None:
    # Lazy: flush imports the models, and this module is imported by auth
    # code that may load before the app registry is ready.
    from api_key_usage.flush import flush_pending_usage

    try:
        flush_pending_usage()
    except Exception:
        logger.exception("API key usage flush failed; it will be retried")
    finally:
        # The thread opened its own connection; nothing else will close it.
        connection.close()
