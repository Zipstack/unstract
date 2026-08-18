"""Behavioural tests for the worker dispatch sites.

Two independent contracts are pinned here so a future change that quietly
drops a field, rewires a queue, or changes an endpoint fails loudly:

1. ``shared/patterns/notification/helper.py`` — status-callback notifications.
   UN-3056 replaced the old ``send_notification_to_worker`` ->
   ``queue_backend.dispatch`` path with a model-free HTTP enqueue:
   ``_route_notification`` -> ``_enqueue_to_buffer`` POSTs each event to the
   backend buffer endpoint, which owns batching + send. These tests
   characterise that HTTP enqueue contract.
2. ``scheduler/tasks.py:_execute_scheduled_workflow`` — still routed through
   the ``queue_backend.dispatch()`` seam (unchanged).
"""

from unittest.mock import MagicMock, patch

import pytest
from shared.patterns.notification.helper import (
    ENQUEUE_BUFFER_ENDPOINT,
    _enqueue_to_buffer,
    _route_notification,
)

from unstract.core.data_models import (
    ExecutionStatus,
    NotificationPayload,
    NotificationSource,
    WorkflowType,
)

# --- Site 1: shared/patterns/notification/helper.py (HTTP buffer enqueue) ---


class TestNotificationDispatchSite:
    """Pin the worker notification path -> backend buffer-enqueue HTTP contract.

    UN-3056 made the callback worker model-free: instead of dispatching a
    Celery task, ``_route_notification`` -> ``_enqueue_to_buffer`` POSTs each
    event to the backend, which owns the NotificationBuffer + clubbed send.
    """

    def _make_notification(self, notification_type="WEBHOOK", platform="API"):
        return {
            "id": "notif-001",
            "notification_type": notification_type,
            "platform": platform,
        }

    def _make_payload(self):
        """A real NotificationPayload so enum -> value coercion is exercised."""
        return NotificationPayload.from_execution_status(
            pipeline_id="pipe-001",
            pipeline_name="char-test-pipeline",
            execution_status=ExecutionStatus.ERROR,
            workflow_type=WorkflowType.API,
            source=NotificationSource.CALLBACK_WORKER,
            execution_id="exec-123",
            error_message="boom",
            total_files=3,
            successful_files=1,
            failed_files=2,
        )

    def test_enqueue_posts_to_buffer_endpoint(self):
        """``_enqueue_to_buffer`` MUST POST to the buffer endpoint, timeout=10."""
        api_client = MagicMock()
        _enqueue_to_buffer(api_client, self._make_notification(), self._make_payload())

        api_client._make_request.assert_called_once()
        call = api_client._make_request.call_args
        assert call.kwargs["method"] == "POST"
        assert call.kwargs["endpoint"] == ENQUEUE_BUFFER_ENDPOINT
        assert call.kwargs["timeout"] == 10

    def test_enqueue_payload_shape(self):
        """The enqueued ``data`` MUST carry the full per-event contract the
        backend buffer + clubbed renderer rely on."""
        api_client = MagicMock()
        _enqueue_to_buffer(api_client, self._make_notification(), self._make_payload())

        data = api_client._make_request.call_args.kwargs["data"]
        assert set(data) == {
            "notification_id",
            "type",
            "execution_id",
            "pipeline_id",
            "pipeline_name",
            "status",
            "error_message",
            "platform",
            "timestamp",
            "additional_data",
        }
        assert data["notification_id"] == "notif-001"
        assert data["pipeline_id"] == "pipe-001"
        assert data["pipeline_name"] == "char-test-pipeline"
        assert data["execution_id"] == "exec-123"
        assert data["platform"] == "API"
        # Enums are coerced to their string values, not passed as objects.
        assert data["type"] == WorkflowType.API.value
        assert isinstance(data["status"], str)
        assert isinstance(data["additional_data"], dict)

    def test_enqueue_raises_on_request_failure(self):
        """A transport failure MUST propagate out of ``_enqueue_to_buffer`` so
        the router can count the drop (it is the only failure signal)."""
        api_client = MagicMock()
        api_client._make_request.side_effect = RuntimeError("backend down")

        with pytest.raises(RuntimeError):
            _enqueue_to_buffer(
                api_client, self._make_notification(), self._make_payload()
            )

    def test_route_skips_non_webhook(self):
        """Non-WEBHOOK notifications MUST NOT be enqueued."""
        api_client = MagicMock()
        _route_notification(
            api_client,
            self._make_notification(notification_type="EMAIL"),
            self._make_payload(),
        )
        api_client._make_request.assert_not_called()

    def test_route_skips_missing_notification_type(self):
        """A malformed notification with no notification_type key is skipped —
        ``.get()`` returns None, which fails the WEBHOOK check (no KeyError)."""
        api_client = MagicMock()
        notification = {"id": "notif-001", "platform": "API"}  # no notification_type
        _route_notification(api_client, notification, self._make_payload())
        api_client._make_request.assert_not_called()

    def test_route_enqueues_webhook(self):
        """WEBHOOK notifications MUST reach the buffer endpoint."""
        api_client = MagicMock()
        _route_notification(api_client, self._make_notification(), self._make_payload())

        api_client._make_request.assert_called_once()
        assert (
            api_client._make_request.call_args.kwargs["endpoint"]
            == ENQUEUE_BUFFER_ENDPOINT
        )

    def test_route_swallows_enqueue_failure(self):
        """An enqueue failure MUST NOT abort the caller's loop — sibling
        notifications still get their turn. ``_route_notification`` is the
        path's final swallow point."""
        api_client = MagicMock()
        api_client._make_request.side_effect = RuntimeError("backend down")

        # Must not raise.
        _route_notification(api_client, self._make_notification(), self._make_payload())
        api_client._make_request.assert_called_once()


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
        """Kwargs MUST contain use_file_history, pipeline_id, and transport.

        ``transport`` (9e) is carried in the task payload so the pipeline stays
        on one transport end-to-end. It defaults to ``"celery"`` when the
        create-execution response omits it (older backend / inert PR 1).
        """
        from scheduler.tasks import _execute_scheduled_workflow

        ctx = self._make_context()
        ctx.use_file_history = True

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(self._make_api_client(), ctx)

        kwargs = mock_dispatch.call_args.kwargs["kwargs"]
        assert kwargs == {
            "use_file_history": True,
            "pipeline_id": "pipe-007",
            "transport": "celery",
        }

    def test_dispatch_carries_backend_resolved_transport(self):
        """The transport the backend returns from create-execution is threaded
        verbatim into the dispatched task's payload (payload-carry, 9e)."""
        from scheduler.tasks import _execute_scheduled_workflow

        api = MagicMock()
        api.create_workflow_execution.return_value = {
            "execution_id": "exec-123",
            "transport": "pg_queue",
        }

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(api, self._make_context())

        assert mock_dispatch.call_args.kwargs["kwargs"]["transport"] == "pg_queue"

    def test_pg_transport_routes_dispatch_to_pg_backend(self):
        """The one line that actually routes the scheduled orchestrator onto PG:
        transport=="pg_queue" → dispatch(backend=QueueBackend.PG) (identity, not
        the allow-list)."""
        from queue_backend import QueueBackend
        from scheduler.tasks import _execute_scheduled_workflow

        api = MagicMock()
        api.create_workflow_execution.return_value = {
            "execution_id": "exec-123",
            "transport": "pg_queue",
        }
        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(api, self._make_context())

        assert mock_dispatch.call_args.kwargs["backend"] is QueueBackend.PG

    def test_celery_transport_leaves_backend_none(self):
        """transport=="celery" → backend=None (legacy Celery dispatch unchanged)."""
        from scheduler.tasks import _execute_scheduled_workflow

        with patch("scheduler.tasks.dispatch") as mock_dispatch:
            _execute_scheduled_workflow(self._make_api_client(), self._make_context())

        assert mock_dispatch.call_args.kwargs["backend"] is None

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
        """Zero raw Celery dispatch calls should exist in workers/ source
        outside the queue_backend/ seam.

        ``queue_backend/dispatch.py`` is the canonical home: it's the
        one file that calls ``current_app.send_task`` (today, while the
        substrate is still Celery). Everything else must call
        ``queue_backend.dispatch(...)`` instead.

        Uses an AST walker rather than a regex so the canary covers:

        * aliased imports (``from celery import current_app as app``;
          ``app.send_task(...)``),
        * locally-constructed apps (``Celery(...).send_task(...)``),
        * ``.apply_async`` (the other half of how Celery sends tasks,
          including ``signature(...).apply_async()``),
        * multi-line dotted access after autoformatter wrap.
        """
        import ast
        import pathlib

        workers_root = pathlib.Path(__file__).parent.parent
        # Anchor skip to the top-level directory relative to workers_root so
        # we don't accidentally exclude legitimately-named subdirectories
        # (e.g. workers/shared/tests_helpers/).
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv", "queue_backend"}
        # ``plugins/manual_review`` predates this seam and uses
        # ``task.apply_async`` lambda overrides to inject queues — out of
        # scope for the queue_backend transport seam PR. Tracked as a
        # follow-up so this canary is exact for everything we own.
        skip_subpaths = {"plugins/manual_review"}
        forbidden_attrs = {"send_task", "apply_async"}

        class DispatchCallFinder(ast.NodeVisitor):
            def __init__(self) -> None:
                self.hits: list[int] = []

            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
                    self.hits.append(node.lineno)
                self.generic_visit(node)

        hits: list[str] = []
        for py in workers_root.rglob("*.py"):
            rel = py.relative_to(workers_root)
            rel_parts = rel.parts
            if rel_parts and rel_parts[0] in skip_top_dirs:
                continue
            rel_str = rel.as_posix()
            if any(rel_str.startswith(skip + "/") for skip in skip_subpaths):
                continue
            try:
                tree = ast.parse(py.read_text(), filename=str(py))
            except SyntaxError:
                continue
            finder = DispatchCallFinder()
            finder.visit(tree)
            for line_no in finder.hits:
                hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        assert hits == [], (
            "Raw Celery dispatch call(s) (send_task / apply_async) found "
            "outside queue_backend/. All task dispatch must go through "
            "queue_backend.dispatch(). Found:\n  " + "\n  ".join(hits)
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


# --- Site 1b: early-failure dispatch (notify_execution_failure) ---


class TestEarlyFailureNotification:
    """Pin the early-failure notification path (UN-3056).

    Runs that fail before file processing (missing-tool / tool-validation /
    source-setup errors) never reach the callback's
    ``handle_status_notifications``, so the general worker calls
    ``notify_execution_failure`` on its failure branch. It must resolve the
    pipeline name/type from the backend and dispatch a terminal ERROR status;
    if pipeline data can't be fetched it must skip rather than raise.
    """

    def _api_client(self, *, success=True, data="default"):
        api_client = MagicMock()
        resp = MagicMock()
        resp.success = success
        resp.data = (
            {"pipeline": {"pipeline_name": "etl-early-fail", "pipeline_type": "ETL"}}
            if data == "default"
            else data
        )
        api_client.get_pipeline_data.return_value = resp
        return api_client

    def test_dispatches_terminal_error_with_resolved_identity(self):
        from shared.patterns.notification import helper as notif_helper

        api_client = self._api_client()
        with patch.object(notif_helper, "handle_status_notifications") as mock_dispatch:
            notif_helper.notify_execution_failure(
                api_client=api_client,
                pipeline_id="pipe-1",
                execution_id="exec-1",
                organization_id="org-1",
                error_message="Tool does not exist in registry: text_extractor",
            )

        api_client.get_pipeline_data.assert_called_once_with(
            pipeline_id="pipe-1", check_active=False
        )
        mock_dispatch.assert_called_once()
        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["pipeline_id"] == "pipe-1"
        assert kwargs["status"] == ExecutionStatus.ERROR.value
        assert kwargs["pipeline_name"] == "etl-early-fail"
        assert kwargs["pipeline_type"] == "ETL"
        assert kwargs["execution_id"] == "exec-1"
        assert kwargs["organization_id"] == "org-1"
        assert "text_extractor" in kwargs["error_message"]

    def test_skips_when_pipeline_data_unavailable(self):
        from shared.patterns.notification import helper as notif_helper

        api_client = self._api_client(success=False, data=None)
        with patch.object(notif_helper, "handle_status_notifications") as mock_dispatch:
            notif_helper.notify_execution_failure(
                api_client=api_client,
                pipeline_id="pipe-1",
                execution_id="exec-1",
                organization_id="org-1",
            )

        mock_dispatch.assert_not_called()

    def test_resolves_flat_pipeline_shape(self):
        # Older backend builds return the record flat (no "pipeline" envelope).
        from shared.patterns.notification import helper as notif_helper

        api_client = self._api_client(
            data={"pipeline_name": "flat-etl", "pipeline_type": "TASK"}
        )
        with patch.object(notif_helper, "handle_status_notifications") as mock_dispatch:
            notif_helper.notify_execution_failure(
                api_client=api_client,
                pipeline_id="pipe-1",
                execution_id="exec-1",
                organization_id="org-1",
            )

        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["pipeline_name"] == "flat-etl"
        assert kwargs["pipeline_type"] == "TASK"

    def test_does_not_raise_when_resolution_errors(self):
        # A backend hiccup while resolving identity must not bubble out of the
        # worker's failure handler (it is best-effort, post-status-update).
        from shared.patterns.notification import helper as notif_helper

        api_client = MagicMock()
        api_client.get_pipeline_data.side_effect = RuntimeError("backend down")
        with patch.object(notif_helper, "handle_status_notifications") as mock_dispatch:
            notif_helper.notify_execution_failure(
                api_client=api_client,
                pipeline_id="pipe-1",
                execution_id="exec-1",
                organization_id="org-1",
            )

        mock_dispatch.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
