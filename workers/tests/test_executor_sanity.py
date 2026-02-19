"""Phase 1 Sanity Check — Executor worker integration tests.

These tests verify the full executor chain works end-to-end.

Verifies:
1. Worker enums and registry configuration
2. ExecutorToolShim works from workers venv
3. NoOpExecutor registers and executes via orchestrator
4. Celery task wiring (execute_extraction task logic)
5. Full dispatch -> task -> orchestrator -> executor round-trip
6. Retry configuration on the task
"""

import pytest
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure a clean executor registry for every test."""
    ExecutorRegistry.clear()
    yield
    ExecutorRegistry.clear()


def _make_context(**overrides):
    defaults = {
        "executor_name": "noop",
        "operation": "extract",
        "run_id": "run-sanity-001",
        "execution_source": "tool",
        "organization_id": "org-test",
        "request_id": "req-sanity-001",
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _register_noop():
    """Register a NoOpExecutor for testing."""

    @ExecutorRegistry.register
    class NoOpExecutor(BaseExecutor):
        @property
        def name(self):
            return "noop"

        def execute(self, context):
            return ExecutionResult(
                success=True,
                data={"echo": context.operation, "run_id": context.run_id},
                metadata={"executor": self.name},
            )


# --- 1. Worker enums and registry ---


class TestWorkerEnumsAndRegistry:
    """Verify executor is properly registered in worker infrastructure."""

    def test_worker_type_executor_exists(self):
        from shared.enums.worker_enums import WorkerType

        assert WorkerType.EXECUTOR.value == "executor"

    def test_queue_name_executor_exists(self):
        from shared.enums.worker_enums import QueueName

        assert QueueName.EXECUTOR.value == "executor"

    def test_task_name_execute_extraction_exists(self):
        from shared.enums.task_enums import TaskName

        assert TaskName.EXECUTE_EXTRACTION.value == "execute_extraction"

    def test_health_port_is_8088(self):
        from shared.enums.worker_enums import WorkerType

        assert WorkerType.EXECUTOR.to_health_port() == 8088

    def test_worker_registry_has_executor_config(self):
        from shared.enums.worker_enums import WorkerType
        from shared.infrastructure.config.registry import WorkerRegistry

        config = WorkerRegistry.get_queue_config(WorkerType.EXECUTOR)
        assert "executor" in config.all_queues()

    def test_task_routing_includes_execute_extraction(self):
        from shared.enums.worker_enums import WorkerType
        from shared.infrastructure.config.registry import WorkerRegistry

        routing = WorkerRegistry.get_task_routing(WorkerType.EXECUTOR)
        patterns = [r.pattern for r in routing.routes]
        assert "execute_extraction" in patterns


# --- 2. ExecutorToolShim ---


class TestExecutorToolShim:
    """Verify the real ExecutorToolShim works in the workers venv."""

    def test_import(self):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(platform_api_key="sk-test")
        assert shim.platform_api_key == "sk-test"

    def test_platform_key_returned(self):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(platform_api_key="sk-real-key")
        assert shim.get_env_or_die("PLATFORM_SERVICE_API_KEY") == "sk-real-key"

    def test_env_var_from_environ(self, monkeypatch):
        from executor.executor_tool_shim import ExecutorToolShim

        monkeypatch.setenv("TEST_SHIM_VAR", "hello")
        shim = ExecutorToolShim(platform_api_key="sk-test")
        assert shim.get_env_or_die("TEST_SHIM_VAR") == "hello"

    def test_missing_var_raises(self):
        from executor.executor_tool_shim import ExecutorToolShim
        from unstract.sdk1.exceptions import SdkError

        shim = ExecutorToolShim(platform_api_key="sk-test")
        with pytest.raises(SdkError, match="NONEXISTENT"):
            shim.get_env_or_die("NONEXISTENT")

    def test_stream_log_does_not_print_json(self, capsys):
        """stream_log routes to logging, not stdout JSON."""
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(platform_api_key="sk-test")
        shim.stream_log("test message")
        captured = capsys.readouterr()
        # Should NOT produce JSON on stdout (that's the old protocol)
        assert '"type": "LOG"' not in captured.out

    def test_stream_error_raises_sdk_error(self):
        from executor.executor_tool_shim import ExecutorToolShim
        from unstract.sdk1.exceptions import SdkError

        shim = ExecutorToolShim(platform_api_key="sk-test")
        with pytest.raises(SdkError, match="boom"):
            shim.stream_error_and_exit("boom")


# --- 3. NoOpExecutor via Orchestrator ---


class TestNoOpExecutorOrchestrator:
    """Verify a NoOpExecutor works through the orchestrator."""

    def test_noop_executor_round_trip(self):
        _register_noop()

        ctx = _make_context(operation="extract")
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute(ctx)

        assert result.success is True
        assert result.data == {"echo": "extract", "run_id": "run-sanity-001"}

    def test_unknown_executor_fails_gracefully(self):
        orchestrator = ExecutionOrchestrator()
        ctx = _make_context(executor_name="nonexistent")
        result = orchestrator.execute(ctx)

        assert result.success is False
        assert "nonexistent" in result.error


# --- 4 & 5. Full chain with Celery eager mode ---
#
# executor/worker.py imports executor/tasks.py which defines
# execute_extraction as a shared_task.  We import the real app,
# configure it for eager mode, and exercise the actual task.


@pytest.fixture
def eager_app():
    """Configure the real executor Celery app for eager-mode testing."""
    from executor.worker import app

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
    """Verify the execute_extraction task configuration."""

    def test_task_is_registered(self, eager_app):
        assert "execute_extraction" in eager_app.tasks

    def test_task_has_retry_config(self, eager_app):
        task = eager_app.tasks["execute_extraction"]
        assert task.max_retries == 3
        assert ConnectionError in task.autoretry_for
        assert TimeoutError in task.autoretry_for
        assert OSError in task.autoretry_for

    def test_task_retry_backoff_enabled(self, eager_app):
        task = eager_app.tasks["execute_extraction"]
        assert task.retry_backoff is True
        assert task.retry_jitter is True


class TestFullChainEager:
    """End-to-end test using Celery's eager mode.

    task_always_eager=True makes tasks execute inline in the
    calling process — full chain without a broker.
    """

    def _run_task(self, eager_app, context_dict):
        """Run execute_extraction task via task.apply() (eager-safe)."""
        task = eager_app.tasks["execute_extraction"]
        result = task.apply(args=[context_dict])
        return result.get()

    def test_eager_dispatch_round_trip(self, eager_app):
        """Execute task inline, verify result comes back."""
        _register_noop()

        ctx = _make_context(operation="answer_prompt", run_id="run-eager")
        result_dict = self._run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data["echo"] == "answer_prompt"
        assert result.data["run_id"] == "run-eager"
        assert result.metadata.get("executor") == "noop"

    def test_eager_dispatch_invalid_context(self, eager_app):
        """Invalid context dict returns failure result (not exception)."""
        result_dict = self._run_task(eager_app, {"bad": "data"})
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "Invalid execution context" in result.error

    def test_eager_dispatch_unknown_executor(self, eager_app):
        """Unknown executor returns failure (no unhandled exceptions)."""
        ctx = _make_context(executor_name="does_not_exist")
        result_dict = self._run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "does_not_exist" in result.error

    def test_result_serialization_round_trip(self, eager_app):
        """Verify ExecutionResult survives Celery serialization."""
        _register_noop()

        ctx = _make_context(
            operation="single_pass_extraction",
            executor_params={"schema": {"name": "str", "age": "int"}},
        )
        result_dict = self._run_task(eager_app, ctx.to_dict())

        # Verify the raw dict is JSON-compatible
        import json

        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)

        result = ExecutionResult.from_dict(deserialized)
        assert result.success is True
        assert result.data["echo"] == "single_pass_extraction"
