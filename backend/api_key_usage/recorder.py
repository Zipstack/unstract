"""Count a key's use when it authenticates a request, without a database write.

Each use is one Redis script call, so a flush sees all of a use or none of it.
The counts wait in the ``PENDING_*`` hashes until ``flush.flush_pending_usage``
moves them to the database. Recording also triggers that flush, at most once
per ``API_KEY_USAGE_FLUSH_INTERVAL_SECONDS`` across every process, and runs it
in a background thread so the request that triggers it does not wait.

Hash fields, joined by ``FIELD_SEPARATOR``:

* ``PENDING_CALLS``: ``key_type|key_id|organization_id|day`` -> call count
* ``PENDING_LAST_USED``: ``key_type|key_id|organization_id`` -> epoch seconds
* ``PENDING_CALLERS``: ``key_type|key_id|organization_id|api_deployment_id|day``
  -> call count
* ``PENDING_CALLER_LAST``: same field as ``PENDING_CALLERS`` -> epoch seconds

Timestamps only move forward, so a request that records late never replaces a
newer use.
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

# KEYS: calls, last_used, callers, caller_last, flush_due.
# ARGV: calls field, key field, seen, caller field ("" for none), interval.
# Returns 1 when this use set the flush trigger.
_RECORD = """
local function keep_latest(hash, field, seen)
    local current = redis.call('hget', hash, field)
    if not current or tonumber(current) < tonumber(seen) then
        redis.call('hset', hash, field, seen)
    end
end
redis.call('hincrby', KEYS[1], ARGV[1], 1)
keep_latest(KEYS[2], ARGV[2], ARGV[3])
if ARGV[4] ~= '' then
    redis.call('hincrby', KEYS[3], ARGV[4], 1)
    keep_latest(KEYS[4], ARGV[4], ARGV[3])
end
if redis.call('set', KEYS[5], 1, 'NX', 'EX', ARGV[5]) then
    return 1
end
return 0
"""


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
        key = join_field(key_type, key_id, organization_id)
        caller = join_field(key, api_deployment_id, day) if api_deployment_id else ""

        flush_due = get_redis_connection("default").eval(
            _RECORD,
            5,
            PENDING_CALLS,
            PENDING_LAST_USED,
            PENDING_CALLERS,
            PENDING_CALLER_LAST,
            FLUSH_DUE_KEY,
            join_field(key, day),
            key,
            repr(at.timestamp()),
            caller,
            settings.API_KEY_USAGE_FLUSH_INTERVAL_SECONDS,
        )
    except Exception:
        # The key's identifiers stay out of the log: its type is enough to
        # tell which auth path lost a count.
        logger.exception("Could not record an API key use (%s)", key_type)
        return

    if flush_due:
        start_background_flush()


def start_background_flush() -> None:
    """Run a flush in a daemon thread. Tests replace this to flush inline."""
    if not settings.API_KEY_USAGE_BACKGROUND_FLUSH:
        return
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
