import logging
import time

from django.conf import settings
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

_SLOT_TTL_SECONDS = 6 * 3600


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
            logger.warning("agent-kv concurrency limiter failing open", exc_info=True)
            return True

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
        logger.warning("agent-kv key rate limiter failing open", exc_info=True)
        return True
