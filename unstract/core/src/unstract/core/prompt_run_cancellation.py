"""Cancellation signal for Prompt Studio runs (UN-1031).

A Prompt Studio run has no interruptible handle. The POST returns ``202`` after
dispatching, the PG queue transport exposes only ``send/read/set_vt/delete`` (no
revoke, no dead-letter), and the consumer runs the task eagerly in-process — so
nothing can preempt a claimed task from the outside. Cancellation is therefore
**cooperative**: the backend records an intent, and the worker checks it at
stage boundaries where stopping is cheap and safe.

The intent lives in Redis, keyed on ``run_id`` — the only identifier that spans
every stage of a run (extract, index, answer_prompt) and that the browser knows
before the first response comes back. The value is a set whose members are the
prompt ids to cancel, or :data:`WHOLE_RUN` for "stop everything in this run".
Per-prompt granularity matters because one bulk ``answer_prompt`` task loops
over many prompts: stopping one must not discard the others.

Every read is **best effort**. If Redis is unreachable the answer is "not
cancelled" and the run completes normally — the worst case is that a user's
Stop does nothing, never that a healthy run dies or that a worker wedges.

Both the backend (Django) and the workers import this module; it deliberately
speaks raw Redis via :func:`unstract.core.cache.redis_client.create_redis_client`
with the canonical ``REDIS_`` prefix rather than Django's cache or the workers'
``CACHE_REDIS_*`` config, because those two resolve to *different* Redis
databases in the Helm chart and the signal must be visible to both sides.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Final

import redis

from unstract.core.cache.redis_client import create_redis_client

logger = logging.getLogger(__name__)

__all__ = [
    "CANCEL_TTL_SECONDS",
    "PROMPT_RUN_CANCELLED_ERROR",
    "WHOLE_RUN",
    "cancel_key",
    "cancelled_prompt_ids",
    "clear_cancel",
    "is_cancelled",
    "remember_run_owner",
    "request_cancel",
    "run_owner",
]

# Sentinel member meaning "cancel the whole run", as opposed to a prompt id.
# A run id is a UUID and a prompt id is a UUID, so "*" can never collide.
WHOLE_RUN: Final = "*"

# Error text a cancelled stage reports. Every layer (executor -> consumer ->
# callback -> socket) matches on this exact string to tell a user-requested stop
# apart from a real failure, so it MUST NOT be reworded in one place only.
PROMPT_RUN_CANCELLED_ERROR: Final = "Prompt run cancelled by user"

# Retention for a cancel record. Must outlive the longest run a worker can hold,
# which is bounded by the executor's visibility timeout (7200s in the Helm chart,
# 3660s in compose) — so a late checkpoint still sees the intent. It is an
# intent, not state: nothing reads it after the run ends.
CANCEL_TTL_SECONDS: Final = 7260

_KEY_PREFIX: Final = "ps:cancel:"

# Records which tool a run belongs to, so a cancel can be checked against the
# tool it is being requested through. A run id is minted in the browser and
# never persisted relationally, so without this there is nothing server-side
# tying a run to anything (UN-1031).
_OWNER_PREFIX: Final = "ps:run-tool:"

# Cooldown before rebuilding a Redis client that failed to build. A transient
# blip (restart/failover) must not disable cancellation for the life of the
# process, but we also must not attempt a rebuild on every checkpoint — the
# checkpoints run in tight per-prompt loops. Mirrors the same guard in the
# workers' ``PgResultBackend`` result signal.
_CLIENT_RETRY_COOLDOWN_SECONDS: Final = 30.0

_client_singleton: redis.Redis | None = None
_client_last_failure: float | None = None


def cancel_key(org_id: str, run_id: str) -> str:
    """Redis key holding the cancel intent for one run.

    Only ids are ever sent to Redis — never prompt text, document content or any
    other payload.
    """
    return f"{_KEY_PREFIX}{org_id}:{run_id}"


def owner_key(org_id: str, run_id: str) -> str:
    """Redis key recording which tool dispatched one run."""
    return f"{_OWNER_PREFIX}{org_id}:{run_id}"


def remember_run_owner(org_id: str, run_id: str, tool_id: str) -> None:
    """Record that *run_id* was dispatched by *tool_id*.

    Best effort: a run whose owner could not be recorded simply cannot be
    checked later, which is the behaviour that predates this record. Never
    raises — a signal-store blip must not stop a run from being dispatched.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.set(owner_key(org_id, run_id), tool_id, ex=CANCEL_TTL_SECONDS)
    except Exception:
        logger.warning(
            "prompt-run cancellation: could not record the owner of run_id=%s",
            run_id,
            exc_info=True,
        )


def run_owner(org_id: str, run_id: str) -> str | None:
    """The tool that dispatched *run_id*, or ``None`` if not recorded.

    ``None`` is genuinely "unknown", not "no owner": Redis may be unreachable,
    or the run may predate this record. Callers must decide what an unknown
    owner means for them.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        value = client.get(owner_key(org_id, run_id))
    except Exception:
        logger.warning(
            "prompt-run cancellation: could not read the owner of run_id=%s",
            run_id,
            exc_info=True,
        )
        return None
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _get_client() -> redis.Redis | None:
    """Return the process-cached Redis client, or ``None`` if it can't be built.

    A build failure is time-stamped rather than latched, so a Redis restart
    self-heals once the cooldown elapses.
    """
    global _client_singleton, _client_last_failure
    if _client_singleton is not None:
        return _client_singleton
    if (
        _client_last_failure is not None
        and time.monotonic() - _client_last_failure < _CLIENT_RETRY_COOLDOWN_SECONDS
    ):
        return None
    try:
        _client_singleton = create_redis_client(
            env_prefix="REDIS_",
            decode_responses=True,
            # Short timeouts: a checkpoint sits on the critical path of a run, so
            # a wedged Redis must degrade to "not cancelled" fast rather than add
            # latency to every prompt.
            socket_connect_timeout=_socket_timeout(),
            socket_timeout=_socket_timeout(),
        )
        _client_last_failure = None
    except Exception:
        _client_last_failure = time.monotonic()
        logger.warning(
            "prompt-run cancellation: could not build the Redis client; cancel "
            "checks degrade to 'not cancelled' (retry after cooldown)",
            exc_info=True,
        )
    return _client_singleton


def _socket_timeout() -> int:
    """Socket timeout for the cancel client, overridable for slow environments."""
    try:
        return max(1, int(os.getenv("PROMPT_CANCEL_REDIS_TIMEOUT", "2")))
    except ValueError:
        return 2


def _reset_client() -> None:
    """Drop the cached client so the next call rebuilds it (used by tests and by
    the error paths below, where a dead connection must not be reused forever).
    """
    global _client_singleton, _client_last_failure
    _client_singleton = None
    _client_last_failure = time.monotonic()


def request_cancel(org_id: str, run_id: str, prompt_ids: list[str] | None = None) -> bool:
    """Record the intent to cancel *run_id*.

    Args:
        org_id: Tenant scope; part of the key so tenants never collide.
        prompt_ids: Prompt ids to stop, or ``None`` to stop the whole run
            (recorded as :data:`WHOLE_RUN`). An empty list is treated as
            ``None`` — "stop this run" is the only sensible reading of a Stop
            with nothing named.

    Returns:
        ``True`` if the intent was recorded. ``False`` means Redis was
        unreachable and the run will continue; the caller should surface that
        rather than telling the user the run was stopped.
    """
    client = _get_client()
    if client is None:
        return False
    members = list(prompt_ids) if prompt_ids else [WHOLE_RUN]
    key = cancel_key(org_id, run_id)
    try:
        pipe = client.pipeline()
        pipe.sadd(key, *members)
        pipe.expire(key, CANCEL_TTL_SECONDS)
        pipe.execute()
    except Exception:
        logger.warning(
            "prompt-run cancellation: could not record cancel for run_id=%s",
            run_id,
            exc_info=True,
        )
        _reset_client()
        return False
    logger.info(
        "prompt-run cancellation: recorded cancel for run_id=%s members=%s",
        run_id,
        members,
    )
    return True


def cancelled_prompt_ids(org_id: str, run_id: str) -> frozenset[str]:
    """Return the recorded cancel members for *run_id*.

    An empty set means "nothing cancelled" and is also what an unreachable Redis
    yields, by design — see the module docstring on best-effort reads.
    """
    if not run_id:
        return frozenset()
    client = _get_client()
    if client is None:
        return frozenset()
    try:
        return frozenset(client.smembers(cancel_key(org_id, run_id)))
    except Exception:
        logger.warning(
            "prompt-run cancellation: could not read cancel state for run_id=%s; "
            "treating as not cancelled",
            run_id,
            exc_info=True,
        )
        _reset_client()
        return frozenset()


def is_cancelled(org_id: str, run_id: str, prompt_id: str | None = None) -> bool:
    """Whether work for *run_id* (optionally narrowed to *prompt_id*) should stop.

    Without ``prompt_id`` this answers "is the whole run cancelled?" — a
    per-prompt Stop does NOT abort stages shared by the run (extract, index),
    because the run's other prompts still need them.
    """
    members = cancelled_prompt_ids(org_id, run_id)
    if not members:
        return False
    if WHOLE_RUN in members:
        return True
    return prompt_id is not None and prompt_id in members


def clear_cancel(org_id: str, run_id: str) -> None:
    """Drop the cancel record for *run_id*. Best effort; the TTL is the backstop.

    Used when a run is re-dispatched under a reused ``run_id`` so a stale intent
    cannot stop the new run.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(cancel_key(org_id, run_id))
    except Exception:
        logger.warning(
            "prompt-run cancellation: could not clear cancel for run_id=%s; the TTL "
            "will expire it",
            run_id,
            exc_info=True,
        )
