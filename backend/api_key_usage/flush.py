"""Move pending API key usage from Redis to the database.

A flush moves every pending hash, in one atomic step, into a batch named by a
token, so uses recorded while it runs land in fresh hashes for the next flush.
It then applies each batch waiting in Redis, its own and any a failed or killed
flush left behind: the counts and the batch's token are written in one
transaction, and only after that commits is the batch deleted from Redis. A
batch whose token is already written is only deleted, so no count is added
twice and none is lost. A batch that keeps failing is set aside after
``MAX_BATCH_ATTEMPTS``, so one bad batch cannot hold up the others. An outage
(the database or Redis unreachable) ends the flush without counting against any
batch, so every batch waits in Redis until the outage is over.

The background flush also deletes rows older than ``RETENTION_DAYS``. A flush
before a read skips that, so reads stay quick.

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
from django.db import InterfaceError, OperationalError, connection, transaction
from django.utils import timezone
from psycopg2.extras import execute_values
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from api_key_usage import recorder
from api_key_usage.constants import (
    APPLIED_BATCH_KEEP_DAYS,
    BATCH_FAILURES_KEY,
    BATCH_PREFIX,
    BATCHES_KEY,
    DEAD_BATCH_KEEP_DAYS,
    DEAD_BATCHES_KEY,
    FIELD_SEPARATOR,
    FLUSH_LOCK_KEY,
    FLUSH_LOCK_SECONDS,
    MAX_BATCH_ATTEMPTS,
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
    failed: int = 0
    set_aside: int = 0


@dataclass
class _Pending:
    calls: dict[str, int] = field(default_factory=dict)
    last_used: dict[str, float] = field(default_factory=dict)
    callers: dict[str, int] = field(default_factory=dict)
    caller_last: dict[str, float] = field(default_factory=dict)


def flush_pending_usage(prune: bool = True) -> FlushResult:
    """Write pending usage to the database. Returns at once if a flush is running.

    A batch that cannot be written is logged and stays in Redis for the next
    flush; the other batches are still written. An outage stops the flush
    without counting a failure, since retrying the others would fail too.
    ``prune`` also deletes rows outside the retention window.
    """
    # The recorder's client: short socket timeouts, so a stalled Redis fails
    # this flush instead of hanging the read that started it.
    redis = recorder.redis_client()
    lock = uuid.uuid4().hex
    if not redis.set(FLUSH_LOCK_KEY, lock, nx=True, ex=FLUSH_LOCK_SECONDS):
        return FlushResult(skipped=True)
    try:
        result = FlushResult()
        _take_pending(redis, uuid.uuid4().hex)
        for token in sorted(_text(t) for t in redis.smembers(BATCHES_KEY)):
            try:
                _apply_batch(redis, token, result)
            except _OUTAGE_ERRORS:
                if _backends_up(redis):
                    # The connections work, so the batch itself fails, e.g. a
                    # statement timeout or deadlock that recurs every time.
                    logger.exception("Could not write API key usage batch %s", token)
                    _count_failure(redis, token, result)
                    continue
                logger.warning(
                    "API key usage flush stopped: database or Redis unavailable; "
                    "pending batches are kept for the next flush",
                    exc_info=True,
                )
                result.failed += 1
                return result
            except Exception:
                logger.exception("Could not write API key usage batch %s", token)
                _count_failure(redis, token, result)
        if prune:
            result.pruned = _prune(timezone.now())
        if any((result.calls, result.pruned, result.dropped, result.failed)):
            logger.info("API key usage flush: %s", result)
        return result
    finally:
        redis.eval(_RELEASE_LOCK, 1, FLUSH_LOCK_KEY, lock)


# Errors that may mean an outage rather than a bad batch. Which one it is
# depends on whether the connections still work (``_backends_up``).
_OUTAGE_ERRORS = (
    OperationalError,
    InterfaceError,
    RedisConnectionError,
    RedisTimeoutError,
)


def _backends_up(redis) -> bool:
    """Whether the database and Redis both answer right now."""
    try:
        connection.ensure_connection()
        return connection.is_usable() and bool(redis.ping())
    except Exception:
        return False


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
    redis.hdel(BATCH_FAILURES_KEY, token)


def _count_failure(redis, token: str, result: FlushResult) -> None:
    """Count a failed attempt at batch ``token``; set it aside after too many."""
    result.failed += 1
    if redis.hincrby(BATCH_FAILURES_KEY, token, 1) < MAX_BATCH_ATTEMPTS:
        return
    for name in _batch_names(token):
        redis.expire(name, timedelta(days=DEAD_BATCH_KEEP_DAYS))
    redis.sadd(DEAD_BATCHES_KEY, token)
    redis.srem(BATCHES_KEY, token)
    redis.hdel(BATCH_FAILURES_KEY, token)
    result.set_aside += 1
    logger.error(
        "API key usage batch %s failed %s times and was set aside",
        token,
        MAX_BATCH_ATTEMPTS,
    )


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
        execute_values(
            cursor,
            f"""
            INSERT INTO {ApiKeyUsageDaily._meta.db_table}
                (organization_id, key_type, key_id, day, calls)
            VALUES %s
            ON CONFLICT (key_type, key_id, day)
            DO UPDATE SET calls = {ApiKeyUsageDaily._meta.db_table}.calls
                + EXCLUDED.calls
            """,
            rows,
        )
        result.calls += sum(row[-1] for row in rows)

        rows = [(*key, at) for key, at in last_used.items() if key[0] in live]
        result.dropped += len(last_used) - len(rows)
        execute_values(
            cursor,
            f"""
            INSERT INTO {ApiKeyLastUsed._meta.db_table}
                (organization_id, key_type, key_id, last_used_at)
            VALUES %s
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
        execute_values(
            cursor,
            f"""
            INSERT INTO {ApiKeyCallerDaily._meta.db_table}
                (organization_id, key_type, key_id, api_deployment_id, day,
                 calls, last_call_at)
            VALUES %s
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


def _uuid(value: str) -> str:
    return str(uuid.UUID(value))


def _org_id(value: str) -> str:
    return str(int(value))


def _day(value: str) -> str:
    return date.fromisoformat(value).isoformat()


# Each field's parts, by how many there are: key_type, key_id, organization_id,
# then the API deployment id (callers only), then the day (counts only).
_PARTS = {
    3: (str, _uuid, _org_id),
    4: (str, _uuid, _org_id, _day),
    5: (str, _uuid, _org_id, _uuid, _day),
}


def _split(fld: str, parts: int, result: FlushResult) -> list[str] | None:
    """The field's parts, or None (logged and counted as dropped) if malformed.

    Each part is checked against the column it goes to, and a bad field is
    dropped rather than raised: a raise would fail the whole batch.
    """
    values = fld.split(FIELD_SEPARATOR)
    try:
        if len(values) != parts:
            raise ValueError
        return [check(value) for check, value in zip(_PARTS[parts], values, strict=True)]
    except ValueError:
        logger.warning("Dropping malformed pending API key usage field %r", fld)
        result.dropped += 1
        return None


def _at(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value
