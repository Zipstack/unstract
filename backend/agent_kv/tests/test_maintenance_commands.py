"""Management-command entrypoints for the Agent-KV maintenance jobs.

Same no-test-DB style as the rest of ``agent_kv/tests``: real Django app
registry via ``django.setup()``, no database. ``agent_kv.maintenance``'s two
entrypoints are patched so no query ever runs -- their own behaviour
(candidate queries, guard semantics, batching) is covered where it lives now,
``agent_kv/maintenance.py``, exercised indirectly through the views in
``test_sweeps.py``. What's pinned here is only the command<->function wiring:
each command calls its maintenance function exactly once, with no arguments,
and writes the returned dict to stdout as JSON -- the shape a Kubernetes
CronJob log line needs.
"""

import json
import os
from io import StringIO
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.management import call_command  # noqa: E402

from agent_kv import maintenance  # noqa: E402


@mock.patch.object(maintenance, "run_sweep")
def test_agent_kv_sweep_command_calls_run_sweep_once_and_prints_its_result(
    m_run_sweep,
):
    m_run_sweep.return_value = {"swept": 2, "timed_out": 1}
    out = StringIO()

    call_command("agent_kv_sweep", stdout=out)

    m_run_sweep.assert_called_once_with()
    assert json.loads(out.getvalue()) == {"swept": 2, "timed_out": 1}


@mock.patch.object(maintenance, "run_ttl_cleanup")
def test_agent_kv_ttl_cleanup_command_calls_run_ttl_cleanup_once_and_prints_its_result(
    m_run_ttl_cleanup,
):
    m_run_ttl_cleanup.return_value = {"cleaned": 5}
    out = StringIO()

    call_command("agent_kv_ttl_cleanup", stdout=out)

    m_run_ttl_cleanup.assert_called_once_with()
    assert json.loads(out.getvalue()) == {"cleaned": 5}
