"""Single source of truth for the PG-queue rollout flag key.

One Flipt flag gates the whole PG-queue feature — execution
(``workflow_v2/transport.py``), scheduler (``scheduler/ownership.py``), and
executor (``pg_queue/executor_rpc.py``) all read this one key. Kept in a neutral
leaf module so the three resolvers import a single constant instead of
duplicating the literal (a grep on ``PG_QUEUE_FLAG_KEY`` finds every use), making
"one flag" a structural guarantee. This flag is the **sole** rollout control —
fail-closed to Celery on a blind/unreachable Flipt or any error.
"""

PG_QUEUE_FLAG_KEY = "pg_queue_enabled"
