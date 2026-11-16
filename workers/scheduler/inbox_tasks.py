"""Thin PG-side task for the daily inbox purge.

Fired by the PG scheduler from the ``inbox_purge`` row (backend inbox migration
0002). It POSTs to the backend, which deletes inbox items older than 90 days.
"""

from typing import Any

from queue_backend import worker_task
from scheduler.dashboard_metrics_tasks import _call_internal


@worker_task(name="inbox.purge")
def inbox_purge() -> dict[str, Any]:
    return _call_internal("v1/inbox/purge/")
