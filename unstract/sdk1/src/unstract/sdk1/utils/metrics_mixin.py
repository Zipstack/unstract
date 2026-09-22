import logging
import os
import time
import uuid
from typing import Any

from unstract.core.cache.redis_client import create_redis_client

logger = logging.getLogger(__name__)

_DEFAULT_DB = 1


def _metrics_redis_db() -> int:
    """Which logical database the `metrics:*` keys live on (UN-4123).

    Default 1 is the database this has always used, so an unset var leaves every
    existing deployment exactly as it was. It exists so a SINGLE-DATABASE endpoint
    can be supported: Azure Managed Redis, Redis Enterprise and every cluster-mode
    service expose db 0 only, and this was the last place in the codebase where a
    database was chosen in code rather than in configuration.

    Set it alongside CACHE_REDIS_DB and FILE_ACTIVE_CACHE_REDIS_DB — those three
    are the whole of Unstract's on-prem database map.

    An explicit db argument beats a REDIS_URL's /<db> path — create_redis_client
    strips the path for exactly this caller — so this works in URL mode too.

    A blank value means UNSET, not malformed: a declared-but-empty variable is this
    repo's own convention for "leave the default" (CACHE_REDIS_PASSWORD=,
    REDIS_SSL_CA_CERTS=), and every other variable in this work treats it that way.
    Without that, int("") raised inside __init__'s try/except and every LLM timing
    metric went silently missing platform-wide, once per instrumented call, behind
    a log line that named Redis rather than this variable.

    A genuinely unparseable value falls back to the default and says so, for the
    same reason: losing every metric is a bad trade for a typo.
    """
    raw = os.getenv("METRICS_REDIS_DB", "").strip() or "1"
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid METRICS_REDIS_DB=%r; falling back to db %s", raw, _DEFAULT_DB
        )
        return _DEFAULT_DB


class MetricsMixin:
    TIME_TAKEN_KEY = "time_taken(s)"

    def __init__(self, run_id: str) -> None:
        """Initialize the MetricsMixin class.

        Args:
            run_id (str): Unique identifier for the run.
        """
        self.run_id = run_id
        self.op_id = str(uuid.uuid4())  # Unique identifier for this instance
        self.redis_client = None
        try:
            self.redis_client = create_redis_client(db=_metrics_redis_db())
        except Exception as e:
            logger.error(f"Failed to initialize Redis client for run_id={run_id}: {e}")

        self.redis_key = f"metrics:{self.run_id}:{self.op_id}"

        # Set the start time immediately upon initialization
        self.set_start_time()

    def set_start_time(self, ttl: int = 86400) -> None:
        """Store the current timestamp in Redis when the instance is created."""
        if self.redis_client is None:
            logger.error("Redis client is not initialized. Cannot set start time.")
            return
        try:
            self.redis_client.set(self.redis_key, time.time(), ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set start time in Redis: {e}")
            self.redis_client = None

    def collect_metrics(self) -> dict[str, Any]:
        """Calculate the time taken since the timestamp was set and delete the Redis key.

        Returns:
            dict: The calculated time taken and the associated run_id and op_id.
        """
        if self.redis_client is None:
            return {self.TIME_TAKEN_KEY: None}

        try:
            if not self.redis_client.exists(self.redis_key):
                return {self.TIME_TAKEN_KEY: None}

            start_time = float(self.redis_client.get(self.redis_key))
            time_taken = round(time.time() - start_time, 3)

            self.redis_client.delete(self.redis_key)

            return {self.TIME_TAKEN_KEY: time_taken}
        except Exception as e:
            logger.error(f"Failed to collect metrics from Redis: {e}")
            return {self.TIME_TAKEN_KEY: None}
