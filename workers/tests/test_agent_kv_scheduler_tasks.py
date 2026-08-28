"""Tests for the thin Agent-KV maintenance-periodic proxy tasks (spec §5.4).

Mirrors ``test_dashboard_metrics_tasks.py``'s style: these tasks do nothing but
call the shared ``InternalAPIClient`` facade, so what's worth pinning is the
registered wire name (a mismatch means the PG consumer drops the message as an
unknown task -- the failure mode with no error at the enqueue site) and which
client method each task calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import via the PACKAGE, matching `scheduler/tasks.py`'s
# `from scheduler import agent_kv_tasks` -- see that file's comment and
# `test_dashboard_metrics_tasks.py`'s identical note on why this form (not a
# bare `import agent_kv_tasks`) is the one both runtime import mechanisms
# converge on.
_WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKERS_ROOT))

from scheduler import agent_kv_tasks as akt  # noqa: E402
from shared.api import InternalAPIClient  # noqa: E402


class TestRegistration:
    """The wire name is this task pair's own new contract (no pre-existing
    Beat/PG-scheduler row to mirror) -- a rename here silently breaks whatever
    PgPeriodicTask row an operator registered against the old name.
    """

    @pytest.mark.parametrize(
        "name,func",
        [
            ("agent_kv.sweep", "agent_kv_sweep"),
            ("agent_kv.ttl_cleanup", "agent_kv_ttl_cleanup"),
        ],
    )
    def test_task_is_registered_under_its_wire_name(self, name, func):
        assert getattr(akt, func).name == name


class TestApiClientAcquisition:
    def test_get_api_client_returns_an_internal_api_client(self):
        with patch("shared.api.InternalAPIClient") as mock_cls:
            akt._get_api_client()
        mock_cls.assert_called_once_with()


class TestCallContract:
    def test_sweep_calls_the_sweep_client_method(self):
        mock_api = MagicMock()
        mock_api.agent_kv_sweep.return_value = {"swept": 3, "timed_out": 1}
        with patch.object(akt, "_get_api_client", return_value=mock_api):
            result = akt.agent_kv_sweep()
        mock_api.agent_kv_sweep.assert_called_once_with()
        assert result == {"swept": 3, "timed_out": 1}

    def test_ttl_cleanup_calls_the_ttl_cleanup_client_method(self):
        mock_api = MagicMock()
        mock_api.agent_kv_ttl_cleanup.return_value = {"cleaned": 2}
        with patch.object(akt, "_get_api_client", return_value=mock_api):
            result = akt.agent_kv_ttl_cleanup()
        mock_api.agent_kv_ttl_cleanup.assert_called_once_with()
        assert result == {"cleaned": 2}


class TestInternalClientAgentKvMethods:
    """The client methods (``workers/shared/api/internal_client.py``) the tasks
    above call -- pinned separately so a change to either the endpoint path or
    the call contract fails at the right layer.
    """

    def test_agent_kv_sweep_posts_to_the_sweep_endpoint(self):
        with patch.object(
            InternalAPIClient, "post", return_value={"swept": 1, "timed_out": 0}
        ) as m_post:
            client = InternalAPIClient.__new__(InternalAPIClient)
            result = client.agent_kv_sweep()
        m_post.assert_called_once_with("v1/agent-kv/sweep/", data={})
        assert result == {"swept": 1, "timed_out": 0}

    def test_agent_kv_ttl_cleanup_posts_to_the_ttl_cleanup_endpoint(self):
        with patch.object(
            InternalAPIClient, "post", return_value={"cleaned": 1}
        ) as m_post:
            client = InternalAPIClient.__new__(InternalAPIClient)
            result = client.agent_kv_ttl_cleanup()
        m_post.assert_called_once_with("v1/agent-kv/ttl-cleanup/", data={})
        assert result == {"cleaned": 1}
