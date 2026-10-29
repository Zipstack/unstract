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

# Set with NX and an expiry of the flush interval: whoever sets it flushes,
# so recording triggers at most one flush per interval across all processes.
FLUSH_DUE_KEY = "api_key_usage:flush_due"

# Held only while a flush runs, so two flushes never move the same data.
FLUSH_LOCK_KEY = "api_key_usage:flush_lock"
FLUSH_LOCK_SECONDS = 60

FIELD_SEPARATOR = "|"
