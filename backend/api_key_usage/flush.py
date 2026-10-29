"""Move pending API key usage from Redis to the database.

A flush moves every pending hash, in one atomic step, into a batch named by a
token, so uses recorded while it runs land in fresh hashes for the next flush.
It then applies each batch waiting in Redis, its own and any a failed or killed
flush left behind: the counts and the batch's token are written in one
transaction, and only after that commits is the batch deleted from Redis. A
batch whose token is already written is only deleted, so no count is added
twice and none is lost. A flush also deletes rows older than ``RETENTION_DAYS``.

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

from api_key_usage.constants import (
    APPLIED_BATCH_KEEP_DAYS,
    BATCH_PREFIX,
    BATCHES_KEY,
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
from api_key_usage.models import (
    ApiKeyCallerDaily,
    ApiKeyLastUsed,
    ApiKeyUsageAppliedBatch,
    ApiKeyUsageDaily,
)

logger = logging.getLogger(__name__)

# Deletes the lock only if this flush still holds it, so a flush that outlived
# its lock never releases another flush's.
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

# KEYS: the pending hashes, then their batch names in the same order, then
# BATCHES_KEY. ARGV: the batch token. Moves whichever pending hashes exist and
# lists the batch, all in one step.
_TAKE = """
local count = (#KEYS - 1) / 2
local moved = false
for i = 1, count do
    if redis.call('exists', KEYS[i]) == 1 then
        redis.call('rename', KEYS[i], KEYS[i + count])
        moved = true
    end
end
if moved then
    redis.call('sadd', KEYS[#KEYS], ARGV[1])
end
return moved and 1 or 0
"""


@dataclass
class FlushResult:
    """What one flush wrote. ``skipped`` means another flush held the lock."""

    skipped: bool = False
    batches: int = 0
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


def flush_pending_usage() -> FlushResult:
    """Write pending usage to the database. Returns at once if a flush is running.

    Raises if a batch cannot be written; that batch and any after it stay in
    Redis for the next flush.
    """
    redis = get_redis_connection("default")
    lock = uuid.uuid4().hex
    if not redis.set(FLUSH_LOCK_KEY, lock, nx=True, ex=FLUSH_LOCK_SECONDS):
        return FlushResult(skipped=True)
    try:
        result = FlushResult()
        _take_pending(redis, uuid.uuid4().hex)
        for token in sorted(_text(t) for t in redis.smembers(BATCHES_KEY)):
            _apply_batch(redis, token, result)
        result.pruned = _prune(timezone.now())
        if result.calls or result.pruned or result.dropped:
            logger.info("API key usage flush: %s", result)
        return result
    finally:
        redis.eval(_RELEASE_LOCK, 1, FLUSH_LOCK_KEY, lock)


def _batch_names(token: str) -> list[str]:
    return [f"{BATCH_PREFIX}:{token}:{name}" for name in PENDING_HASHES]


def _take_pending(redis, token: str) -> None:
    """Move the pending hashes into batch ``token``, if anything is pending."""
    keys = [*PENDING_HASHES, *_batch_names(token), BATCHES_KEY]
    redis.eval(_TAKE, len(keys), *keys, token)


def _read_batch(redis, token: str) -> _Pending:
    raw = {
        name: {_text(k): _text(v) for k, v in redis.hgetall(batch_name).items()}
        for name, batch_name in zip(PENDING_HASHES, _batch_names(token), strict=True)
    }
    return _Pending(
        calls={k: int(v) for k, v in raw[PENDING_CALLS].items()},
        last_used={k: float(v) for k, v in raw[PENDING_LAST_USED].items()},
        callers={k: int(v) for k, v in raw[PENDING_CALLERS].items()},
        caller_last={k: float(v) for k, v in raw[PENDING_CALLER_LAST].items()},
    )


def _apply_batch(redis, token: str, result: FlushResult) -> None:
    """Write batch ``token`` once, then delete it from Redis."""
    pending = _read_batch(redis, token)
    with transaction.atomic():
        _, created = ApiKeyUsageAppliedBatch.objects.get_or_create(token=token)
        if created:
            _write(pending, result)
            result.batches += 1
    redis.delete(*_batch_names(token))
    redis.srem(BATCHES_KEY, token)


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
        result.calls += sum(row[-1] for row in rows)

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
        result.last_used += len(rows)

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
        result.callers += len(rows)


def _prune(now: datetime) -> int:
    """Delete daily rows outside the last ``RETENTION_DAYS`` UTC days."""
    cutoff = oldest_kept_day(now)
    pruned, _ = ApiKeyUsageDaily.objects.filter(day__lt=cutoff).delete()
    callers, _ = ApiKeyCallerDaily.objects.filter(day__lt=cutoff).delete()
    ApiKeyUsageAppliedBatch.objects.filter(
        applied_at__lt=now - timedelta(days=APPLIED_BATCH_KEEP_DAYS)
    ).delete()
    return pruned + callers


def oldest_kept_day(now: datetime) -> date:
    """First UTC day of the retention window, today included."""
    return now.astimezone(UTC).date() - timedelta(days=RETENTION_DAYS - 1)


def _split(fld: str, parts: int, result: FlushResult) -> list[str] | None:
    """The field's parts, or None (logged and counted as dropped) if malformed.

    Dropped rather than raised: a raise would keep its batch and fail every
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
