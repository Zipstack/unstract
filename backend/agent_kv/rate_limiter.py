import logging
import time

from django.conf import settings
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


def _limiter_failure_allows_request() -> bool:
    """Whether a request proceeds when the limiter backend is unreachable.

    Fails CLOSED unless `AGENT_KV_LIMITER_FAIL_OPEN` is explicitly set. Both
    limiters previously returned True on any Redis exception, which is the one
    choice that cannot be observed from the outside: a Sentinel failover
    silently removed the concurrency ceiling AND the per-key rate ceiling at the
    same time, and the API went on accepting billable LLM work as if both still
    held. Closed is the safer default for a paid, concurrency-capped API -- a
    429 is recoverable by the caller, an unbounded fan-out is not.

    The waiver remains available because availability-over-accounting is a
    legitimate operational choice, but it now has to be made deliberately, in
    config, where it is visible -- rather than being the implicit behaviour of
    an `except` block.
    """
    return bool(getattr(settings, "AGENT_KV_LIMITER_FAIL_OPEN", False))


#: How long a held slot survives in Redis without being released. Public
#: because the sweep needs it: past this age there is nothing left to release,
#: which is what bounds its cancelled-job scan.
SLOT_TTL_SECONDS = 6 * 3600
_SLOT_TTL_SECONDS = SLOT_TTL_SECONDS


def _redis():
    # Same handle acquisition as api_v2.rate_limiter (`redis_cache =
    # get_redis_connection("default")`); api_v2 has no reusable helper to
    # call into, so the construction line is copied here rather than
    # modifying api_v2.
    return get_redis_connection("default")


class AgentKVConcurrencyLimiter:
    @staticmethod
    def _key(organization_id: str) -> str:
        return f"agent_kv:inflight:{organization_id}"

    # Trim stale slots, count, and claim a slot in ONE atomic server-side
    # step. A client-side ``ZCARD`` followed by ``ZADD`` is a check-then-act
    # race: N simultaneous submits all observe ``count < limit`` and all get
    # accepted (caught live in the Task 13b run: 6 concurrent submits against
    # a limit of 5 produced six 202s). Redis runs a script atomically, so at
    # most ``limit`` members can ever be added.
    _ACQUIRE_SCRIPT = """
local key = KEYS[1]
redis.call('ZREMRANGEBYSCORE', key, 0, ARGV[3])
if redis.call('ZCARD', key) >= tonumber(ARGV[4]) then
  return 0
end
redis.call('ZADD', key, ARGV[2], ARGV[1])
redis.call('EXPIRE', key, ARGV[5])
return 1
"""

    @classmethod
    def check_and_acquire(cls, organization_id: str, job_id: str) -> bool:
        try:
            r = _redis()
            now = time.time()
            key = cls._key(organization_id)
            acquired = r.eval(
                cls._ACQUIRE_SCRIPT,
                1,
                key,
                job_id,
                now,
                now - _SLOT_TTL_SECONDS,
                settings.AGENT_KV_CONCURRENT_LIMIT,
                _SLOT_TTL_SECONDS,
            )
            return bool(int(acquired))
        except Exception:
            # Fail CLOSED by default. Both this ceiling and the per-key rate
            # ceiling used to `return True` on any Redis error, so a single
            # Sentinel failover or pool exhaustion removed BOTH at once while
            # the API kept returning 202s for billable LLM work -- with nothing
            # but a per-request `logger.warning` to show for it.
            #
            # `logger.exception` (not warning): the limiter being unavailable is
            # an error, and the old level is what let this sit unnoticed.
            logger.exception("agent-kv concurrency limiter unavailable")
            return _limiter_failure_allows_request()

    @classmethod
    def release(cls, organization_id: str, job_id: str) -> None:
        try:
            _redis().zrem(cls._key(organization_id), job_id)
        except Exception:
            logger.warning("agent-kv slot release failed", exc_info=True)


def check_key_rate(key_id: str) -> bool:
    try:
        r = _redis()
        window = int(time.time() // 60)
        key = f"agent_kv:rate:{key_id}:{window}"
        count = r.incr(key)
        r.expire(key, 120)
        return count <= settings.AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE
    except Exception:
        logger.exception("agent-kv key rate limiter unavailable")
        return _limiter_failure_allows_request()
