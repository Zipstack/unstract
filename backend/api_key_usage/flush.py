"""Move pending API key usage from Redis to the database.

A flush renames each pending hash out of the way, so uses recorded while it
runs land in a fresh hash for the next flush, then adds the counts to the
daily tables in one transaction. If the write fails, the counts are put back
and the next flush retries them. A flush also deletes rows older than
``RETENTION_DAYS``.

Runs from ``recorder.record_key_use`` (in the background, at most once per
interval) and before a read that wants current numbers. It needs no scheduler,
so usage is recorded the same way whichever queue backend is running.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from account_v2.models import Organization
from django.db import connection, transaction
from django.utils import timezone
from django_redis import get_redis_connection
from redis.exceptions import ResponseError

from api_key_usage.constants import (
    FIELD_SEPARATOR,
    FLUSH_LOCK_KEY,
    FLUSH_LOCK_SECONDS,
    PENDING_CALLER_LAST,
    PENDING_CALLERS,
    PENDING_CALLS,
    PENDING_HASHES,
    PENDING_LAST_USED,
    RETENTION_DAYS,
)
from api_key_usage.models import ApiKeyCallerDaily, ApiKeyLastUsed, ApiKeyUsageDaily

logger = logging.getLogger(__name__)

# Deletes the lock only if this flush still holds it, so a flush that outlived
# its lock never releases another flush's.
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass
class FlushResult:
    """What one flush wrote. ``skipped`` means another flush held the lock."""

    skipped: bool = False
    calls: int = 0
    last_used: int = 0
    callers: int = 0
    pruned: int = 0
    dropped: int = 0


@dataclass
class _Pending:
    calls: dict[str, int] = field(default_factory=dict)
    last_used: dict[str, float] = field(default_factory=dict)
    callers: dict[str, int] = field(default_factory=dict)
    caller_last: dict[str, float] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.calls or self.last_used or self.callers or self.caller_last)


def flush_pending_usage() -> FlushResult:
    """Write pending usage to the database. Returns at once if a flush is running."""
    redis = get_redis_connection("default")
    token = uuid.uuid4().hex
    if not redis.set(FLUSH_LOCK_KEY, token, nx=True, ex=FLUSH_LOCK_SECONDS):
        return FlushResult(skipped=True)
    try:
        pending = _take_pending(redis, token)
        result = FlushResult()
        if not pending.is_empty():
            try:
                _write(pending, result)
            except Exception:
                _restore(redis, pending)
                raise
        result.pruned = _prune(timezone.now())
        if result.calls or result.pruned or result.dropped:
            logger.info("API key usage flush: %s", result)
        return result
    finally:
        redis.eval(_RELEASE_LOCK, 1, FLUSH_LOCK_KEY, token)


def _take_pending(redis, token: str) -> _Pending:
    """Atomically move each pending hash aside and read it."""
    taken = {}
    for name in PENDING_HASHES:
        flushing = f"{name}:flushing:{token}"
        try:
            redis.rename(name, flushing)
        except ResponseError:
            # No such key: nothing was recorded since the last flush.
            taken[name] = {}
            continue
        raw = redis.hgetall(flushing)
        redis.delete(flushing)
        taken[name] = {_text(k): _text(v) for k, v in raw.items()}
    return _Pending(
        calls={k: int(v) for k, v in taken[PENDING_CALLS].items()},
        last_used={k: float(v) for k, v in taken[PENDING_LAST_USED].items()},
        callers={k: int(v) for k, v in taken[PENDING_CALLERS].items()},
        caller_last={k: float(v) for k, v in taken[PENDING_CALLER_LAST].items()},
    )


def _restore(redis, pending: _Pending) -> None:
    """Put counts back after a failed write. Newer timestamps are kept."""
    try:
        pipe = redis.pipeline(transaction=False)
        for name, counts in (
            (PENDING_CALLS, pending.calls),
            (PENDING_CALLERS, pending.callers),
        ):
            for fld, count in counts.items():
                pipe.hincrby(name, fld, count)
        for name, stamps in (
            (PENDING_LAST_USED, pending.last_used),
            (PENDING_CALLER_LAST, pending.caller_last),
        ):
            for fld, seen in stamps.items():
                pipe.hsetnx(name, fld, seen)
        pipe.execute()
    except Exception:
        logger.exception("Could not restore API key usage after a failed flush")


def _write(pending: _Pending, result: FlushResult) -> None:
    calls = defaultdict(int)
    for fld, count in pending.calls.items():
        if parts := _split(fld, 4, result):
            key_type, key_id, org_id, day = parts
            calls[(org_id, key_type, key_id, day)] += count

    last_used = {}
    for fld, seen in pending.last_used.items():
        if parts := _split(fld, 3, result):
            key_type, key_id, org_id = parts
            last_used[(org_id, key_type, key_id)] = _at(seen)

    callers = {}
    for fld in pending.callers.keys() | pending.caller_last.keys():
        if not (parts := _split(fld, 5, result)):
            continue
        key_type, key_id, org_id, deployment_id, day = parts
        seen = pending.caller_last.get(fld)
        callers[(org_id, key_type, key_id, deployment_id, day)] = (
            pending.callers.get(fld, 0),
            _at(seen) if seen is not None else None,
        )

    # An organisation deleted since the use was recorded would fail the whole
    # batch on its foreign key, and then every retry with it.
    org_ids = {key[0] for key in (*calls, *last_used, *callers)}
    live = {
        str(pk)
        for pk in Organization.objects.filter(pk__in=org_ids).values_list("pk", flat=True)
    }

    with transaction.atomic(), connection.cursor() as cursor:
        rows = [(*key, n) for key, n in calls.items() if key[0] in live]
        result.dropped += len(calls) - len(rows)
        cursor.executemany(
            f"""
            INSERT INTO {ApiKeyUsageDaily._meta.db_table}
                (organization_id, key_type, key_id, day, calls)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (key_type, key_id, day)
            DO UPDATE SET calls = {ApiKeyUsageDaily._meta.db_table}.calls
                + EXCLUDED.calls
            """,
            rows,
        )
        result.calls = sum(row[-1] for row in rows)

        rows = [(*key, at) for key, at in last_used.items() if key[0] in live]
        result.dropped += len(last_used) - len(rows)
        cursor.executemany(
            f"""
            INSERT INTO {ApiKeyLastUsed._meta.db_table}
                (organization_id, key_type, key_id, last_used_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (key_type, key_id)
            DO UPDATE SET last_used_at = GREATEST(
                {ApiKeyLastUsed._meta.db_table}.last_used_at,
                EXCLUDED.last_used_at
            )
            """,
            rows,
        )
        result.last_used = len(rows)

        rows = [
            (*key, n, at)
            for key, (n, at) in callers.items()
            if key[0] in live and at is not None
        ]
        result.dropped += len(callers) - len(rows)
        cursor.executemany(
            f"""
            INSERT INTO {ApiKeyCallerDaily._meta.db_table}
                (organization_id, key_type, key_id, api_deployment_id, day,
                 calls, last_call_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (key_type, key_id, api_deployment_id, day)
            DO UPDATE SET
                calls = {ApiKeyCallerDaily._meta.db_table}.calls + EXCLUDED.calls,
                last_call_at = GREATEST(
                    {ApiKeyCallerDaily._meta.db_table}.last_call_at,
                    EXCLUDED.last_call_at
                )
            """,
            rows,
        )
        result.callers = len(rows)


def _prune(now: datetime) -> int:
    """Delete daily rows outside the last ``RETENTION_DAYS`` UTC days."""
    cutoff = oldest_kept_day(now)
    pruned, _ = ApiKeyUsageDaily.objects.filter(day__lt=cutoff).delete()
    callers, _ = ApiKeyCallerDaily.objects.filter(day__lt=cutoff).delete()
    return pruned + callers


def oldest_kept_day(now: datetime) -> date:
    """First UTC day of the retention window, today included."""
    return now.astimezone(UTC).date() - timedelta(days=RETENTION_DAYS - 1)


def _split(fld: str, parts: int, result: FlushResult) -> list[str] | None:
    """The field's parts, or None (logged and counted as dropped) if malformed.

    Dropped rather than raised: a raise would restore the field and fail every
    later flush on it.
    """
    values = fld.split(FIELD_SEPARATOR)
    if len(values) != parts:
        logger.warning("Dropping malformed pending API key usage field %r", fld)
        result.dropped += 1
        return None
    return values


def _at(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
