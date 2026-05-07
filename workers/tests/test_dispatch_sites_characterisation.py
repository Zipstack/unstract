"""Characterisation tests for the two raw `current_app.send_task` dispatch sites.

These are the only two places in workers/ that bypass `@shared_task`-based
dispatch and call `current_app.send_task(...)` directly with a string task
name.  PR #8 (mass `@shared_task` -> `@worker_task` migration) will replace
both with a unified `dispatch()` helper.

This test suite locks down the **current** dispatch contract — task name,
positional args, keyword args, and target queue — so the migration can
be proved equivalent. It does NOT exercise the receiving tasks; it only
captures what is dispatched.

Sites characterised:
1. ``shared/patterns/notification/helper.py:76`` — webhook notification
2. ``scheduler/tasks.py:157`` — scheduled workflow async dispatch
"""

from unittest.mock import MagicMock, patch

import pytest


# --- Site 1: shared/patterns/notification/helper.py ---


class TestNotificationDispatchSite:
    """Characterise ``send_notification_to_worker`` -> ``current_app.send_task``."""

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

        with patch(
            "shared.patterns.notification.helper.current_app"
        ) as mock_app:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
            )

        mock_app.send_task.assert_called_once()
        call = mock_app.send_task.call_args
        assert call.args[0] == "send_webhook_notification"
        assert call.kwargs["queue"] == "notifications"

    def test_dispatch_positional_args_layout(self):
        """Positional args MUST be [url, payload_dict, headers, timeout]."""
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch(
            "shared.patterns.notification.helper.current_app"
        ) as mock_app:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="BEARER",
                auth_key="token-abc",
                auth_header=None,
            )

        args = mock_app.send_task.call_args.kwargs["args"]
        assert len(args) == 4
        assert args[0] == "https://example.com/hook"  # url
        assert args[1] == {"event": "test_event", "id": 42}  # payload_dict
        assert args[2]["Authorization"] == "Bearer token-abc"  # headers
        assert args[3] == 10  # timeout (hard-coded)

    def test_dispatch_kwargs_layout(self):
        """Kwargs MUST contain max_retries, retry_delay, platform."""
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch(
            "shared.patterns.notification.helper.current_app"
        ) as mock_app:
            send_notification_to_worker(
                url="https://example.com/hook",
                payload=self._make_payload(),
                auth_type="NONE",
                auth_key=None,
                auth_header=None,
                max_retries=5,
                platform="SLACK",
            )

        kwargs = mock_app.send_task.call_args.kwargs["kwargs"]
        assert kwargs == {
            "max_retries": 5,
            "retry_delay": 10,
            "platform": "SLACK",
        }

    def test_dispatch_returns_true_on_success(self):
        from shared.patterns.notification.helper import send_notification_to_worker

        with patch("shared.patterns.notification.helper.current_app"):
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

        with patch(
            "shared.patterns.notification.helper.current_app"
        ) as mock_app:
            mock_app.send_task.side_effect = RuntimeError("broker down")
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
    """Characterise ``_execute_scheduled_workflow`` -> ``current_app.send_task``."""

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

        with patch("celery.current_app") as mock_app:
            _execute_scheduled_workflow(self._make_api_client(), self._make_context())

        mock_app.send_task.assert_called_once()
        assert mock_app.send_task.call_args.args[0] == "async_execute_bin"

    def test_dispatch_routes_to_general_queue(self):
        from scheduler.tasks import _execute_scheduled_workflow
        from shared.enums.worker_enums import QueueName

        with patch("celery.current_app") as mock_app:
            _execute_scheduled_workflow(self._make_api_client(), self._make_context())

        assert mock_app.send_task.call_args.kwargs["queue"] == QueueName.GENERAL

    def test_dispatch_positional_args_layout(self):
        """Positional args MUST be [org_id, workflow_id, execution_id, {}, True]."""
        from scheduler.tasks import _execute_scheduled_workflow

        with patch("celery.current_app") as mock_app:
            _execute_scheduled_workflow(
                self._make_api_client(execution_id="exec-xyz"),
                self._make_context(),
            )

        args = mock_app.send_task.call_args.kwargs["args"]
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

        with patch("celery.current_app") as mock_app:
            _execute_scheduled_workflow(self._make_api_client(), ctx)

        kwargs = mock_app.send_task.call_args.kwargs["kwargs"]
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

        with patch("celery.current_app") as mock_app:
            result = _execute_scheduled_workflow(api, self._make_context())

        # The dispatch contract: nothing is sent when execution creation fails.
        mock_app.send_task.assert_not_called()
        # And the function returns an error result (not raised exception).
        assert result.status == SchedulerExecutionStatus.ERROR


# --- Cross-site invariant ---


class TestDispatchSiteInventory:
    """If a third raw current_app.send_task site appears, this test breaks
    so PR #8's migration can't silently miss it."""

    def test_only_two_known_dispatch_sites_in_workers(self):
        """Verify the count of raw current_app.send_task references in
        workers/ source matches the two we have characterised."""
        import pathlib
        import re

        workers_root = pathlib.Path(__file__).parent.parent
        # Skip tests/ and __pycache__/ etc.
        skip_dirs = {"tests", "__pycache__", "htmlcov", ".venv"}

        pattern = re.compile(r"current_app\.send_task\b")
        hits = []
        for py in workers_root.rglob("*.py"):
            if any(part in skip_dirs for part in py.parts):
                continue
            text = py.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        # Expected exactly two — in helper.py and scheduler/tasks.py.
        # If a third appears, this test fails so PR #8 doesn't miss it.
        assert len(hits) == 2, (
            f"Expected exactly 2 raw current_app.send_task sites in workers/, found "
            f"{len(hits)}:\n  " + "\n  ".join(hits)
        )
        # Sanity: the two we know about
        joined = " ".join(hits)
        assert "shared/patterns/notification/helper.py" in joined
        assert "scheduler/tasks.py" in joined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
