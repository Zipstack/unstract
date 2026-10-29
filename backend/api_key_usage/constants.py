"""Shared limits and Redis key names for API key usage."""

from django.conf import settings

# Every Redis key below starts with this. Tests give each parallel worker its
# own prefix, since the workers share one Redis.
_PREFIX = settings.API_KEY_USAGE_REDIS_PREFIX

# Daily counts and callers are kept this long; older rows are pruned on flush.
RETENTION_DAYS = 30

# Pending usage waits in these Redis hashes until the next flush moves it to
# the database. Field layouts are documented in ``recorder.py``.
PENDING_CALLS = f"{_PREFIX}:pending:calls"
PENDING_CALLERS = f"{_PREFIX}:pending:callers"
PENDING_CALLER_LAST = f"{_PREFIX}:pending:caller_last"
PENDING_LAST_USED = f"{_PREFIX}:pending:last_used"
PENDING_HASHES = (
    PENDING_CALLS,
    PENDING_CALLERS,
    PENDING_CALLER_LAST,
    PENDING_LAST_USED,
)

# A flush moves the pending hashes, all at once, into a batch named by a
# token, and lists the token here. A batch stays in Redis until the database
# write that applies it commits, so a flush that dies midway loses nothing:
# the next flush applies the batch.
BATCHES_KEY = f"{_PREFIX}:batches"
BATCH_PREFIX = f"{_PREFIX}:batch"

# Applied batch tokens are kept this long, so a batch a crashed flush applied
# but did not clear from Redis is recognised and not added twice.
APPLIED_BATCH_KEEP_DAYS = 7

# Set with NX and an expiry of the flush interval: whoever sets it flushes,
# so recording triggers at most one flush per interval across all processes.
FLUSH_DUE_KEY = f"{_PREFIX}:flush_due"

# Held only while a flush runs, so two flushes never move the same data.
FLUSH_LOCK_KEY = f"{_PREFIX}:flush_lock"
FLUSH_LOCK_SECONDS = 60

FIELD_SEPARATOR = "|"

# Usage status thresholds, shared by the key lists and the summary.
EXPIRING_WITHIN_DAYS = 7
IDLE_AFTER_DAYS = 90
