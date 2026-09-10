"""Contract tests for the queue-backend seam.

``dispatch()`` enqueues to Postgres — PG is the only transport (UN-4046). Two
layers:

1. **No dispatch may reach Celery.** The canary below asserts that no call site
   can resolve to ``CELERY``, because a producer without a consumer does not just
   lose the work: the messages accumulate in RabbitMQ until it hits its memory
   high-watermark and starts blocking publishers.

2. **@worker_task** must still register a task with the Celery app. That is not
   vestigial — the PG consumer resolves work via ``self._app.tasks.get(name)``, so
   the Celery *registry* stays load-bearing even though the Celery *transport* is
   gone.

The old layer 1 was the mirror image of this: a suite proving ``dispatch()``
produced exactly the same ``current_app.send_task`` call as the raw Celery idiom,
so that adding PG routing could be shown to preserve the Celery default. That
default is what we have now removed, so those cases are gone.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from celery import current_app
from queue_backend import QueueBackend, dispatch, select_backend
from queue_backend.routing import resolve_backend

# --- no Celery producer ---


class TestNoCeleryProducer:
    """The zero-producer canary (UN-4046).

    Any dispatch that resolves to CELERY publishes to RabbitMQ, where — with the
    Celery fleet scaled to zero — nothing drains it. Left unnoticed the queue grows
    until the broker blocks publishers, so this is asserted rather than assumed.
    """

    def test_select_backend_never_resolves_to_celery(self):
        # `select_backend()` takes no argument since UN-4046: the answer cannot
        # depend on the task name, so enumerating names proved nothing. (Sonar
        # flagged the unused parameter; removing it makes that structural.)
        assert select_backend() is QueueBackend.PG

    def test_resolve_backend_defaults_to_pg_without_an_override(self):
        assert resolve_backend("any_task", None) is QueueBackend.PG

    def test_an_explicit_pg_override_is_honoured(self):
        assert resolve_backend("any_task", QueueBackend.PG) is QueueBackend.PG

    def test_dispatch_never_calls_send_task(self):
        client = MagicMock()
        client.send.return_value = 1
        with (
            patch("queue_backend.dispatch.current_app") as mock_app,
            patch("queue_backend.dispatch._get_pg_client", return_value=client),
        ):
            dispatch("send_webhook_notification", args=["a"], queue="notifications")
            dispatch("async_execute_bin", args=["b"], queue="celery")
        mock_app.send_task.assert_not_called()
        assert client.send.call_count == 2


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
        # routing gate that the WORKER_PG_QUEUE_ENABLED_TASKS allow-list
        # drives.
        # The PG-queue barrier work adds the Postgres barrier surface:
        # PgBarrier + its barrier_pg_decr_and_check / barrier_pg_abort tasks,
        # selected when WORKER_BARRIER_BACKEND routes to the PG backend.
        assert set(queue_backend.__all__) == {
            "Barrier",
            "BarrierBackend",
            "BarrierHandle",
            "CeleryChordBarrier",
            "FairnessKey",
            "PgBarrier",
            "QueueBackend",
            "RedisDecrBarrier",
            "barrier_abort",
            "barrier_decr_and_check",
            "barrier_pg_abort",
            "barrier_pg_decr_and_check",
            "dispatch",
            "get_barrier",
            "select_backend",
            "worker_task",
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
