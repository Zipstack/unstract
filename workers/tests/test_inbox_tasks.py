"""The inbox purge proxy task calls the backend's internal purge endpoint."""

import sys
from pathlib import Path
from unittest.mock import patch

_WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKERS_ROOT))

from scheduler import inbox_tasks  # noqa: E402
from scheduler import tasks as scheduler_tasks  # noqa: E402


def test_registered_under_the_schedule_rows_task_name():
    assert inbox_tasks.inbox_purge.name == "inbox.purge"


def test_posts_to_the_purge_endpoint():
    with patch.object(inbox_tasks, "_call_internal", return_value={"deleted": 3}) as call:
        assert inbox_tasks.inbox_purge() == {"deleted": 3}
    assert call.call_args[0][0] == "v1/inbox/purge/"


def test_scheduler_worker_registers_the_module():
    assert inbox_tasks in scheduler_tasks._PERIODIC_TASK_MODULES
