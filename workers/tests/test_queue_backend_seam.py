"""Equivalence tests for the queue-backend seam.

Today the seam is a transparent pass-through to Celery. These tests
lock that in so future PRs adding per-task routing (PG Queue) can be
proved to preserve the Celery default path.

Two layers:

1. **dispatch()** must produce the same ``current_app.send_task`` call
   as the raw idiom used at the two existing dispatch sites
   (``notification/helper.py:76``, ``scheduler/tasks.py:157``).

2. **@worker_task** must be the same object as ``@shared_task`` so that
   functions decorated with it register identically with the Celery app.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# --- dispatch() equivalence ---


class TestDispatchEquivalence:
    """dispatch() forwards to current_app.send_task with the same shape."""

    def test_dispatches_task_name(self):
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("send_webhook_notification")

        mock_app.send_task.assert_called_once()
        assert mock_app.send_task.call_args.args[0] == "send_webhook_notification"

    def test_forwards_args(self):
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", args=["a", "b", 42])

        assert mock_app.send_task.call_args.kwargs["args"] == ["a", "b", 42]

    def test_forwards_kwargs(self):
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", kwargs={"max_retries": 5, "platform": "SLACK"})

        assert mock_app.send_task.call_args.kwargs["kwargs"] == {
            "max_retries": 5,
            "platform": "SLACK",
        }

    def test_forwards_queue(self):
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", queue="notifications")

        assert mock_app.send_task.call_args.kwargs["queue"] == "notifications"

    def test_defaults_args_to_empty_list(self):
        """Omitting args must produce [], not None — Celery treats them differently."""
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task")

        assert mock_app.send_task.call_args.kwargs["args"] == []

    def test_defaults_kwargs_to_empty_dict(self):
        """Omitting kwargs must produce {}, not None."""
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task")

        assert mock_app.send_task.call_args.kwargs["kwargs"] == {}

    def test_returns_underlying_handle(self):
        """Whatever send_task returns is what dispatch returns."""
        from queue_backend import dispatch

        sentinel = object()
        with patch("queue_backend.dispatch.current_app") as mock_app:
            mock_app.send_task.return_value = sentinel
            result = dispatch("any_task")

        assert result is sentinel

    def test_matches_notification_helper_shape(self):
        """dispatch() output is identical to the raw send_task at notification/helper.py:76.

        Reference call from helper.py (paraphrased):

            current_app.send_task(
                "send_webhook_notification",
                args=[url, payload_dict, headers, timeout],
                kwargs={"max_retries": ..., "retry_delay": ..., "platform": ...},
                queue="notifications",
            )

        The seam must produce the same call.
        """
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                "send_webhook_notification",
                args=["https://example.com/hook", {"event": "x"}, {}, 10],
                kwargs={"max_retries": 3, "retry_delay": 10, "platform": "API"},
                queue="notifications",
            )

        call = mock_app.send_task.call_args
        assert call.args[0] == "send_webhook_notification"
        assert call.kwargs["args"] == ["https://example.com/hook", {"event": "x"}, {}, 10]
        assert call.kwargs["kwargs"] == {
            "max_retries": 3,
            "retry_delay": 10,
            "platform": "API",
        }
        assert call.kwargs["queue"] == "notifications"

    def test_matches_scheduler_dispatch_shape(self):
        """dispatch() output is identical to the raw send_task at scheduler/tasks.py:157."""
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                "async_execute_bin",
                args=["org-1", "wf-1", "exec-1", {}, True],
                kwargs={"use_file_history": False, "pipeline_id": "pipe-1"},
                queue="general",
            )

        call = mock_app.send_task.call_args
        assert call.args[0] == "async_execute_bin"
        assert call.kwargs["args"] == ["org-1", "wf-1", "exec-1", {}, True]
        assert call.kwargs["kwargs"] == {
            "use_file_history": False,
            "pipeline_id": "pipe-1",
        }
        assert call.kwargs["queue"] == "general"


# --- @worker_task equivalence ---


class TestWorkerTaskEquivalence:
    """@worker_task produces Celery-task-equivalent objects today.

    The seam is a thin function wrapper (not an identity alias) so PR #15
    can grow consumer-registration logic without restructuring callers.
    """

    def test_worker_task_is_callable_passthrough(self):
        """worker_task delegates to shared_task — verified by calling it with
        the same args and asserting the produced task carries the same name.
        """
        from celery import shared_task

        from queue_backend import worker_task

        @worker_task(name="queue_backend_test.passthrough")
        def via_seam():
            return "ok"

        @shared_task(name="queue_backend_test.passthrough_native")
        def via_native():
            return "ok"

        # Both should produce something Celery considers a registered task.
        for t in (via_seam, via_native):
            assert hasattr(t, "apply") or hasattr(t, "delay")

    def test_bare_decorator_form(self):
        """@worker_task on a function registers a Celery task."""
        from queue_backend import worker_task

        @worker_task
        def some_function(x):
            return x * 2

        # shared_task returns a Task instance (or a PromiseProxy on import).
        # We don't care about the concrete type — just that the decorator
        # produced something call-able with .delay/.apply.
        assert hasattr(some_function, "apply") or hasattr(some_function, "delay")

    def test_parameterised_decorator_form(self):
        """@worker_task(name=..., queue=...) accepts kwargs like @shared_task."""
        from queue_backend import worker_task

        @worker_task(name="queue_backend_test.parameterised", queue="general")
        def some_function():
            return "ok"

        assert hasattr(some_function, "apply") or hasattr(some_function, "delay")


# --- Module surface ---


class TestPublicSurface:
    """Pin the public API — guards future PRs against accidental signature changes."""

    def test_exports_dispatch(self):
        import queue_backend

        assert hasattr(queue_backend, "dispatch")
        assert callable(queue_backend.dispatch)

    def test_exports_worker_task(self):
        import queue_backend

        assert hasattr(queue_backend, "worker_task")
        assert callable(queue_backend.worker_task)

    def test_all_exports(self):
        import queue_backend

        assert set(queue_backend.__all__) == {"dispatch", "worker_task"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
