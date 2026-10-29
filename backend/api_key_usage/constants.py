"""Shared limits and Redis key names for API key usage."""

# Daily counts and callers are kept this long; older rows are pruned on flush.
RETENTION_DAYS = 30

# Pending usage waits in these Redis hashes until the next flush moves it to
# the database. Field layouts are documented in ``recorder.py``.
PENDING_CALLS = "api_key_usage:pending:calls"
PENDING_CALLERS = "api_key_usage:pending:callers"
PENDING_CALLER_LAST = "api_key_usage:pending:caller_last"
PENDING_LAST_USED = "api_key_usage:pending:last_used"
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
BATCHES_KEY = "api_key_usage:batches"
BATCH_PREFIX = "api_key_usage:batch"

# Applied batch tokens are kept this long, so a batch a crashed flush applied
# but did not clear from Redis is recognised and not added twice.
APPLIED_BATCH_KEEP_DAYS = 7

# Set with NX and an expiry of the flush interval: whoever sets it flushes,
# so recording triggers at most one flush per interval across all processes.
FLUSH_DUE_KEY = "api_key_usage:flush_due"

# Held only while a flush runs, so two flushes never move the same data.
FLUSH_LOCK_KEY = "api_key_usage:flush_lock"
FLUSH_LOCK_SECONDS = 60

FIELD_SEPARATOR = "|"

# Usage status thresholds, shared by the key lists and the summary.
EXPIRING_WITHIN_DAYS = 7
IDLE_AFTER_DAYS = 90
