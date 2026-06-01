"""Behavioural tests for the two dispatch sites — now routed through the
``queue_backend.dispatch()`` seam.

Both sites used to call ``current_app.send_task(...)`` directly with a
string task name. They now go through ``queue_backend.dispatch(...)``
instead. The dispatch contract — task name, positional args, keyword
args, and target queue — is unchanged by the migration; ``dispatch()``
is a transparent pass-through to ``current_app.send_task`` today.

This suite locks down the contract at each call site so a future change
that quietly drops a kwarg or rewires a queue will fail loudly.

Sites:
1. ``shared/patterns/notification/helper.py:send_notification_to_worker``
2. ``scheduler/tasks.py:_execute_scheduled_workflow``
"""

from unittest.mock import MagicMock, patch

import pytest

# --- Site 1: shared/patterns/notification/helper.py ---


class TestNotificationDispatchSite:
    """Pin ``send_notification_to_worker`` -> ``queue_backend.dispatch``."""

    def _make_payload(self):
        """Build a minimal NotificationPayload-shaped mock.

        The function under test only invokes ``payload.to_webhook_payload()``
        and reads ``payload.pipeline_id`` (for log output).  Anything else
        about the payload object is irrelevant to dispatch behaviour.
        """
        payload = MagicMock()
        payload.to_webhook_payload.return_value = {"event": "test_event", "id": 42}
        payload.pipeline_id = "pipe-001"
        return payload

    def test_dispatch_task_name_and_queue(self):
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.dispatch") as mock_dispatch:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
            )

        mock_dispatch.assert_called_once()
        call = mock_dispatch.call_args
        assert call.args[0] == "send_webhook_notification"
        assert call.kwargs["queue"] == "notifications"

    def test_dispatch_positional_args_layout(self):
        """Positional args MUST be [url, payload_dict, headers, timeout]."""
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.dispatch") as mock_dispatch:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="BEARER",
                auth_key="token-abc",
                auth_header=None,
            )

        args = mock_dispatch.call_args.kwargs["args"]
        assert len(args) == 4
        assert args[0] == "https://example.com/hook"  # url
        assert args[1] == {"event": "test_event", "id": 42}  # payload_dict
        assert args[2]["Authorization"] == "Bearer token-abc"  # headers
        assert args[3] == 10  # timeout (hard-coded)

    def test_dispatch_kwargs_layout(self):
        """Kwargs MUST contain max_retries, retry_delay, platform."""
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.dispatch") as mock_dispatch:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
                max_retries=5,
                platform="SLACK",
            )

        kwargs = mock_dispatch.call_args.kwargs["kwargs"]
        assert kwargs == {
            "max_retries": 5,
            "retry_delay": 10,
            "platform": "SLACK",
        }

    def test_dispatch_returns_true_on_success(self):
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.dispatch"):
            result = send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
            )

        assert result is True

    def test_dispatch_returns_false_on_send_task_failure(self):
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.dispatch") as mock_dispatch:
            mock_dispatch.side_effect = RuntimeError("broker down")
            result = send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
            )

        assert result is False


# --- Site 2: scheduler/tasks.py ---


class TestSchedulerDispatchSite:
    """Pin ``_execute_scheduled_workflow`` -> ``queue_backend.dispatch``."""

    def _make_context(self):
        """Minimal ScheduledPipelineContext-shaped mock.

        The dispatch site reads:
        - context.organization_id, .workflow_id, .pipeline_id, .pipeline_name
        - context.use_file_history
        """
        ctx = MagicMock()
        ctx.organization_id = "org-test"
        ctx.workflow_id = "wf-001"
        ctx.pipeline_id = "pipe-007"
        ctx.pipeline_name = "scheduled-test-pipeline"
        ctx.use_file_history = False
        return ctx

    def _make_api_client(self, execution_id="exec-123"):
        """Mock api_client whose create_workflow_execution returns a dict
        with the expected execution_id."""
        api = MagicMock()
        api.create_workflow_execution.return_value = {"execution_id": execution_id}
        return api

    def test_dispatch_task_name(self):
        from scheduler.tasks import _execute_scheduled_workflow

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(self._make_api_client(), self._make_context())

        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args.args[0] == "async_execute_bin"

    def test_dispatch_routes_to_general_queue(self):
        from scheduler.tasks import _execute_scheduled_workflow
        from shared.enums.worker_enums import QueueName

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(self._make_api_client(), self._make_context())

        assert mock_dispatch.call_args.kwargs["queue"] == QueueName.GENERAL

    def test_dispatch_positional_args_layout(self):
        """Positional args MUST be [org_id, workflow_id, execution_id, {}, True]."""
        from scheduler.tasks import _execute_scheduled_workflow

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(
                self._make_api_client(execution_id="exec-xyz"),
                self._make_context(),
            )

        args = mock_dispatch.call_args.kwargs["args"]
        assert len(args) == 5
        assert args[0] == "org-test"  # organization_id (schema_name)
        assert args[1] == "wf-001"  # workflow_id
        assert args[2] == "exec-xyz"  # execution_id (from api_client return)
        assert args[3] == {}  # hash_values_of_files (always empty for scheduled)
        assert args[4] is True  # scheduled flag (always True here)

    def test_dispatch_kwargs_layout(self):
        """Kwargs MUST contain use_file_history and pipeline_id."""
        from scheduler.tasks import _execute_scheduled_workflow

        ctx = self._make_context()
        ctx.use_file_history = True

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(self._make_api_client(), ctx)

        kwargs = mock_dispatch.call_args.kwargs["kwargs"]
        assert kwargs == {
            "use_file_history": True,
            "pipeline_id": "pipe-007",
        }

    def test_no_dispatch_when_execution_creation_fails(self):
        """If api_client.create_workflow_execution returns no execution_id,
        the function bails out and never calls send_task."""
        from scheduler.tasks import _execute_scheduled_workflow
        from shared.models.scheduler_models import SchedulerExecutionStatus

        api = MagicMock()
        api.create_workflow_execution.return_value = {}  # no execution_id

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            result = _execute_scheduled_workflow(api, self._make_context())

        # The dispatch contract: nothing is sent when execution creation fails.
        mock_dispatch.assert_not_called()
        # And the function returns an error result (not raised exception).
        assert result.status == SchedulerExecutionStatus.ERROR

    def test_dispatch_returns_error_result_when_dispatch_raises(self):
        """If ``dispatch`` raises (broker down, queue gone, etc.),
        ``_execute_scheduled_workflow`` MUST catch it, log, and return a
        ``SchedulerExecutionResult.error(...)`` — NOT propagate the
        exception. This guard makes sure a future routing change can't
        silently flip the failure mode.
        """
        from scheduler.tasks import _execute_scheduled_workflow
        from shared.models.scheduler_models import SchedulerExecutionStatus

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            mock_dispatch.side_effect = RuntimeError("broker down")
            result = _execute_scheduled_workflow(
                self._make_api_client(), self._make_context()
            )

        # Exception was caught (not propagated).
        assert result.status == SchedulerExecutionStatus.ERROR
        # Execution itself was created before the dispatch failed, so the
        # error result is about the dispatch and must carry the
        # execution_id created moments earlier.
        assert result.execution_id == "exec-123"


# --- Cross-site invariant ---


class TestDispatchSiteInventory:
    """All task dispatch must flow through the queue_backend seam.

    Raw ``current_app.send_task`` calls outside ``queue_backend/`` are now
    forbidden — they bypass the substrate-routing chokepoint. If one
    reappears, this test fails so the regression can't ship silently.
    """

    def test_no_raw_dispatch_sites_outside_seam(self):
        """Zero raw ``current_app.send_task`` references should exist in
        workers/ source outside the queue_backend/ seam.

        ``queue_backend/dispatch.py`` is the canonical home: it's the one
        file that calls ``current_app.send_task`` (today, while the
        substrate is still Celery). Everything else must call
        ``queue_backend.dispatch(...)`` instead.
        """
        import pathlib
        import re

        workers_root = pathlib.Path(__file__).parent.parent
        # Anchor skip to the top-level directory relative to workers_root so
        # we don't accidentally exclude legitimately-named subdirectories
        # (e.g. workers/shared/tests_helpers/).
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv", "queue_backend"}

        pattern = re.compile(r"current_app\.send_task\b")
        hits = []
        for py in workers_root.rglob("*.py"):
            rel_parts = py.relative_to(workers_root).parts
            if rel_parts and rel_parts[0] in skip_top_dirs:
                continue
            text = py.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        assert hits == [], (
            "Raw current_app.send_task call(s) found outside queue_backend/. "
            "All task dispatch must go through queue_backend.dispatch(). "
            "Found:\n  " + "\n  ".join(hits)
        )

    def test_canonical_seam_exists(self):
        """The queue_backend/dispatch.py seam must exist — it's where every
        dispatch site routes through. Behavioural equivalence to the
        legacy ``current_app.send_task`` calls is covered by the
        ``TestDispatchEquivalence`` suite in test_queue_backend_seam.py;
        this test only guards the file's existence so a future refactor
        that moves the module by mistake fails loudly.
        """
        import pathlib

        seam = pathlib.Path(__file__).parent.parent / "queue_backend" / "dispatch.py"
        assert seam.exists(), f"Canonical dispatch seam missing: {seam}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
