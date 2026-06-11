"""Equivalence tests for the queue-backend seam.

Today the seam is a transparent pass-through to Celery. These tests
lock that in so future PRs adding per-task routing (PG Queue) can be
proved to preserve the Celery default path.

Two layers:

1. **dispatch()** must produce the same ``current_app.send_task`` call
   as the raw idiom used at the two existing dispatch sites:
   ``shared/patterns/notification/helper.py::send_notification_to_worker``
   and ``scheduler/tasks.py::_execute_scheduled_workflow``.

2. **@worker_task** must register a task with the Celery app so that
   functions decorated with it behave identically to ones decorated
   with ``@shared_task``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery import current_app

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

    def test_omitted_args_forwarded_as_none(self):
        """Omitted ``args`` is forwarded verbatim as ``None``.

        Celery's own ``send_task`` normalises ``None`` to its native default
        (a tuple) internally — the seam doesn't coerce, so any third-party
        router that checks ``isinstance(args, tuple)`` sees Celery's default.
        """
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task")

        assert mock_app.send_task.call_args.kwargs["args"] is None

    def test_omitted_kwargs_forwarded_as_none(self):
        """Same as args — omitted kwargs reaches Celery as ``None``."""
        from queue_backend import dispatch

        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task")

        assert mock_app.send_task.call_args.kwargs["kwargs"] is None

    def test_returns_underlying_handle(self):
        """Whatever send_task returns is what dispatch returns."""
        from queue_backend import dispatch

        sentinel = object()
        with patch("queue_backend.dispatch.current_app") as mock_app:
            mock_app.send_task.return_value = sentinel
            result = dispatch("any_task")

        assert result is sentinel

    def test_matches_notification_helper_shape(self):
        """Output mirrors the raw send_task at ``send_notification_to_worker``.

        Reference call from helper (paraphrased):

            current_app.send_task(
                "send_webhook_notification",
                args=[url, payload_dict, headers, timeout],
                kwargs={"max_retries": ..., "retry_delay": ..., "platform": ...},
                queue="notifications",
            )
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
        """Output mirrors the raw send_task at ``_execute_scheduled_workflow``."""
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
    """@worker_task registers tasks indistinguishably from @shared_task today.

    The seam is a thin function wrapper (not an identity alias) so a later
    phase can grow consumer-registration logic without restructuring callers.
    Assertions go through Celery's task registry so they fail loudly if the
    decorator stops producing real Celery tasks.
    """

    def test_bare_decorator_registers_with_celery(self):
        """@worker_task on a function registers the task by its module-qualified name."""
        from queue_backend import worker_task

        @worker_task
        def queue_backend_test_bare(x):
            return x * 2

        # Force PromiseProxy resolution — MagicMock.name wouldn't survive this.
        resolved_name = queue_backend_test_bare.name
        assert resolved_name in current_app.tasks
        # Round-trip the registered task to confirm it actually runs.
        assert current_app.tasks[resolved_name].apply(args=(3,)).get() == 6

    def test_parameterised_decorator_uses_explicit_name(self):
        """@worker_task(name=..., queue=...) registers under the explicit name."""
        from queue_backend import worker_task

        @worker_task(name="queue_backend_test.parameterised", queue="general")
        def some_function():
            return "ok"

        assert some_function.name == "queue_backend_test.parameterised"
        assert "queue_backend_test.parameterised" in current_app.tasks

    def test_worker_task_matches_shared_task_registration(self):
        """A function decorated with @worker_task is the same kind of object as
        one decorated with @shared_task — same registration semantics, same
        invocation interface.
        """
        from celery import shared_task
        from queue_backend import worker_task

        @worker_task(name="queue_backend_test.via_seam")
        def via_seam():
            return "ok"

        @shared_task(name="queue_backend_test.via_native")
        def via_native():
            return "ok"

        for task, expected_name in (
            (via_seam, "queue_backend_test.via_seam"),
            (via_native, "queue_backend_test.via_native"),
        ):
            assert task.name == expected_name
            assert expected_name in current_app.tasks
            assert current_app.tasks[expected_name].apply().get() == "ok"

    def test_forwards_decorator_kwargs(self):
        """All Celery decorator kwargs reach @shared_task.

        Guards against a refactor like ``return shared_task(*args)`` that
        would silently drop every retry policy, name override, and bind
        flag in the codebase.
        """
        from queue_backend import worker_task

        @worker_task(
            name="queue_backend_test.kwargs",
            bind=True,
            autoretry_for=(ValueError,),
            max_retries=7,
            default_retry_delay=42,
        )
        def with_policy(self):
            return "ok"

        assert with_policy.name == "queue_backend_test.kwargs"
        registered = current_app.tasks["queue_backend_test.kwargs"]
        assert ValueError in (registered.autoretry_for or ())
        assert registered.max_retries == 7
        assert registered.default_retry_delay == 42

    def test_bare_decorator_form_uses_module_qualified_name(self):
        """``@worker_task`` (no parens) gives Celery's auto-generated name."""
        from queue_backend import worker_task

        @worker_task
        def queue_backend_test_auto_named():
            return "ok"

        # Default name is ``<module>.<function>``.
        assert queue_backend_test_auto_named.name.endswith(
            ".queue_backend_test_auto_named"
        )
        assert queue_backend_test_auto_named.name in current_app.tasks


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

        # Phase 6a added Barrier / BarrierHandle / CeleryChordBarrier.
        # Phase 6b adds RedisDecrBarrier + barrier_decr_and_check
        # (registered as a Celery task on import) + the BarrierBackend
        # enum + the get_barrier factory that the WORKER_BARRIER_BACKEND
        # env flag drives.
        # Phase 8a adds QueueBackend + select_backend — the queue-transport
        # routing gate that the WORKER_PG_QUEUE_ENABLED_TASKS / _ORGS
        # allow-lists drive.
        assert set(queue_backend.__all__) == {
            "Barrier",
            "BarrierBackend",
            "BarrierHandle",
            "CeleryChordBarrier",
            "FairnessKey",
            "QueueBackend",
            "RedisDecrBarrier",
            "barrier_abort",
            "barrier_decr_and_check",
            "dispatch",
            "get_barrier",
            "select_backend",
            "worker_task",
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
