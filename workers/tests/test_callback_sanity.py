"""Phase 1 Sanity Check — Callback worker integration tests.

Mirrors test_executor_sanity.py for the callback worker.

Verifies:
1. Worker enums and registry configuration
2. Celery task wiring (process_batch_callback, process_batch_callback_api, healthcheck)
3. Full dispatch -> task round-trip via eager mode (using the simple healthcheck task)
"""

import pytest


# --- 1. Worker enums and registry ---


class TestWorkerEnumsAndRegistry:
    """Verify callback is properly registered in worker infrastructure."""

    def test_worker_type_callback_exists(self):
        from shared.enums.worker_enums import WorkerType

        assert WorkerType.CALLBACK.value == "callback"

    def test_queue_name_callback_exists(self):
        from shared.enums.worker_enums import QueueName

        assert QueueName.CALLBACK.value == "file_processing_callback"

    def test_queue_name_callback_api_exists(self):
        from shared.enums.worker_enums import QueueName

        assert QueueName.CALLBACK_API.value == "api_file_processing_callback"

    def test_task_name_process_batch_callback_exists(self):
        from shared.enums.task_enums import TaskName

        assert TaskName.PROCESS_BATCH_CALLBACK.value == "process_batch_callback"

    def test_health_port_is_8083(self):
        from shared.enums.worker_enums import WorkerType

        assert WorkerType.CALLBACK.to_health_port() == 8083

    def test_worker_registry_has_callback_config(self):
        from shared.enums.worker_enums import WorkerType
        from shared.infrastructure.config.registry import WorkerRegistry

        config = WorkerRegistry.get_queue_config(WorkerType.CALLBACK)
        queues = config.all_queues()
        assert "file_processing_callback" in queues
        assert "api_file_processing_callback" in queues

    def test_task_routing_includes_process_batch_callback(self):
        from shared.enums.worker_enums import WorkerType
        from shared.infrastructure.config.registry import WorkerRegistry

        routing = WorkerRegistry.get_task_routing(WorkerType.CALLBACK)
        patterns = [r.pattern for r in routing.routes]
        assert "process_batch_callback" in patterns


# --- 2 & 3. Celery task wiring + eager round-trip ---
#
# callback/worker.py imports callback/tasks.py which defines the
# callback tasks via @app.task. We import the real app, configure
# it for eager mode, and exercise the simple healthcheck task
# (the only callback task that doesn't require an API client).


@pytest.fixture
def eager_app():
    """Configure the real callback Celery app for eager-mode testing."""
    from callback.worker import app

    original = {
        "task_always_eager": app.conf.task_always_eager,
        "task_eager_propagates": app.conf.task_eager_propagates,
        "result_backend": app.conf.result_backend,
    }

    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )

    yield app

    app.conf.update(original)


class TestCeleryTaskWiring:
    """Verify the callback worker's tasks are registered with the expected config."""

    def test_process_batch_callback_is_registered(self, eager_app):
        assert "process_batch_callback" in eager_app.tasks

    def test_process_batch_callback_api_is_registered(self, eager_app):
        assert "process_batch_callback_api" in eager_app.tasks

    def test_process_batch_callback_django_compat_is_registered(self, eager_app):
        """Backward-compat shim for callbacks dispatched from the Django backend.

        Both this task and `process_batch_callback` delegate to
        `_process_batch_callback_core`, so refactors that touch the core
        (e.g. the upcoming CallbackStatus enum migration) affect this path too.
        """
        assert (
            "workflow_manager.workflow_v2.file_execution_tasks.process_batch_callback"
            in eager_app.tasks
        )

    def test_healthcheck_is_registered(self, eager_app):
        # callback/worker.py registers a healthcheck task on the local app.
        assert any(
            name.endswith(".healthcheck") or name == "healthcheck"
            for name in eager_app.tasks
        )

    def test_process_batch_callback_max_retries_is_zero(self, eager_app):
        """Mirrors Django backend pattern: callback should not auto-retry."""
        task = eager_app.tasks["process_batch_callback"]
        assert task.max_retries == 0

    def test_process_batch_callback_api_has_retry_config(self, eager_app):
        """API variant has autoretry on Exception with backoff + jitter."""
        task = eager_app.tasks["process_batch_callback_api"]
        assert task.max_retries == 3
        assert task.retry_backoff is True
        assert task.retry_jitter is True
        assert Exception in task.autoretry_for


class TestEagerHealthcheckRoundTrip:
    """End-to-end test using Celery eager mode on the simple healthcheck task.

    The full process_batch_callback task requires a configured InternalAPIClient
    and downstream HTTP calls — heavy mocking territory unsuitable for a smoke
    test. The healthcheck task is intentionally simple and gives us a real
    dispatch -> task -> return value round-trip without external dependencies.
    """

    def test_eager_healthcheck_round_trip(self, eager_app):
        # Find the healthcheck task; its module-qualified name varies.
        healthcheck = next(
            t for name, t in eager_app.tasks.items()
            if name.endswith(".healthcheck") or name == "healthcheck"
        )

        result = healthcheck.apply()
        payload = result.get()

        assert payload["status"] == "healthy"
        assert payload["worker_type"] == "callback"
        # task_id may be None in eager mode but the key must be present.
        assert "task_id" in payload
        assert "worker_name" in payload

    def test_healthcheck_result_is_json_serializable(self, eager_app):
        """Verify healthcheck output survives Celery serialization."""
        import json

        healthcheck = next(
            t for name, t in eager_app.tasks.items()
            if name.endswith(".healthcheck") or name == "healthcheck"
        )

        result = healthcheck.apply()
        payload = result.get()

        # The returned dict must round-trip cleanly via JSON without coercion
        # — callback results flow through Celery's JSON serializer, which
        # raises TypeError on non-serializable values (UUIDs, datetimes, etc.).
        # Using `default=str` here would mask exactly the failure mode we want
        # to catch.
        round_tripped = json.loads(json.dumps(payload))
        assert round_tripped["worker_type"] == "callback"
