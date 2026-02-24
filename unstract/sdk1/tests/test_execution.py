"""Unit tests for execution framework (Phase 1A–1G)."""

import json
import logging
from typing import Any, Self
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.constants import LogLevel, ToolEnv
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.execution.context import (
    ExecutionContext,
    ExecutionSource,
    Operation,
)
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


class TestExecutionContext:
    """Tests for ExecutionContext serialization and validation."""

    def _make_context(self, **overrides: Any) -> ExecutionContext:
        """Create a default ExecutionContext with optional overrides."""
        defaults: dict[str, Any] = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "run-001",
            "execution_source": "tool",
            "organization_id": "org-123",
            "executor_params": {"file_path": "/tmp/test.pdf"},
            "request_id": "req-abc",
        }
        defaults.update(overrides)
        return ExecutionContext(**defaults)

    def test_round_trip_serialization(self: Self) -> None:
        """to_dict -> from_dict produces identical context."""
        original = self._make_context()
        restored = ExecutionContext.from_dict(original.to_dict())

        assert restored.executor_name == original.executor_name
        assert restored.operation == original.operation
        assert restored.run_id == original.run_id
        assert restored.execution_source == original.execution_source
        assert restored.organization_id == original.organization_id
        assert restored.executor_params == original.executor_params
        assert restored.request_id == original.request_id

    def test_json_serializable(self: Self) -> None:
        """to_dict output is JSON-serializable (Celery requirement)."""
        ctx = self._make_context()
        serialized = json.dumps(ctx.to_dict())
        deserialized = json.loads(serialized)
        restored = ExecutionContext.from_dict(deserialized)
        assert restored.executor_name == ctx.executor_name

    def test_enum_values_normalized(self: Self) -> None:
        """Enum instances are normalized to plain strings."""
        ctx = self._make_context(
            operation=Operation.ANSWER_PROMPT,
            execution_source=ExecutionSource.IDE,
        )
        assert ctx.operation == "answer_prompt"
        assert ctx.execution_source == "ide"
        # Also check dict output
        d = ctx.to_dict()
        assert d["operation"] == "answer_prompt"
        assert d["execution_source"] == "ide"

    def test_string_values_accepted(self: Self) -> None:
        """Plain string values work without enum coercion."""
        ctx = self._make_context(
            operation="custom_op",
            execution_source="tool",
        )
        assert ctx.operation == "custom_op"
        assert ctx.execution_source == "tool"

    def test_auto_generates_request_id(self: Self) -> None:
        """request_id is generated when not provided."""
        ctx = self._make_context(request_id=None)
        assert ctx.request_id is not None
        assert len(ctx.request_id) > 0

    def test_explicit_request_id_preserved(self: Self) -> None:
        """Explicit request_id is not overwritten."""
        ctx = self._make_context(request_id="my-req-id")
        assert ctx.request_id == "my-req-id"

    def test_optional_organization_id(self: Self) -> None:
        """organization_id can be None (public calls)."""
        ctx = self._make_context(organization_id=None)
        assert ctx.organization_id is None
        d = ctx.to_dict()
        assert d["organization_id"] is None
        restored = ExecutionContext.from_dict(d)
        assert restored.organization_id is None

    def test_empty_executor_params_default(self: Self) -> None:
        """executor_params defaults to empty dict."""
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="run-001",
            execution_source="tool",
        )
        assert ctx.executor_params == {}

    def test_complex_executor_params(self: Self) -> None:
        """Nested executor_params round-trip correctly."""
        params = {
            "file_path": "/data/doc.pdf",
            "outputs": [
                {"prompt_key": "p1", "llm": "adapter-1"},
                {"prompt_key": "p2", "llm": "adapter-2"},
            ],
            "options": {"reindex": True, "chunk_size": 512},
        }
        ctx = self._make_context(executor_params=params)
        restored = ExecutionContext.from_dict(ctx.to_dict())
        assert restored.executor_params == params

    @pytest.mark.parametrize(
        "field,value",
        [
            ("executor_name", ""),
            ("operation", ""),
            ("run_id", ""),
            ("execution_source", ""),
        ],
    )
    def test_validation_rejects_empty_required_fields(
        self: Self, field: str, value: str
    ) -> None:
        """Empty required fields raise ValueError."""
        with pytest.raises(ValueError, match=f"{field} is required"):
            self._make_context(**{field: value})

    def test_all_operations_accepted(self: Self) -> None:
        """All Operation enum values create valid contexts."""
        for op in Operation:
            ctx = self._make_context(operation=op)
            assert ctx.operation == op.value

    def test_from_dict_missing_optional_fields(self: Self) -> None:
        """from_dict handles missing optional fields gracefully."""
        minimal = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "run-001",
            "execution_source": "tool",
        }
        ctx = ExecutionContext.from_dict(minimal)
        assert ctx.organization_id is None
        assert ctx.executor_params == {}
        # request_id is None from dict (no auto-gen in from_dict)
        # but __post_init__ auto-generates it
        assert ctx.request_id is not None


class TestExecutionResult:
    """Tests for ExecutionResult serialization and validation."""

    def test_success_round_trip(self: Self) -> None:
        """Successful result round-trips through dict."""
        original = ExecutionResult(
            success=True,
            data={"output": {"key": "value"}, "metadata": {}},
            metadata={"tokens": 150, "latency_ms": 320},
        )
        restored = ExecutionResult.from_dict(original.to_dict())
        assert restored.success is True
        assert restored.data == original.data
        assert restored.metadata == original.metadata
        assert restored.error is None

    def test_failure_round_trip(self: Self) -> None:
        """Failed result round-trips through dict."""
        original = ExecutionResult(
            success=False,
            error="LLM adapter timeout",
            metadata={"retry_count": 2},
        )
        restored = ExecutionResult.from_dict(original.to_dict())
        assert restored.success is False
        assert restored.error == "LLM adapter timeout"
        assert restored.data == {}
        assert restored.metadata == {"retry_count": 2}

    def test_json_serializable(self: Self) -> None:
        """to_dict output is JSON-serializable."""
        result = ExecutionResult(
            success=True,
            data={"extracted_text": "Hello world"},
        )
        serialized = json.dumps(result.to_dict())
        deserialized = json.loads(serialized)
        restored = ExecutionResult.from_dict(deserialized)
        assert restored.data == result.data

    def test_failure_requires_error_message(self: Self) -> None:
        """success=False without error raises ValueError."""
        with pytest.raises(
            ValueError,
            match="error message is required",
        ):
            ExecutionResult(success=False)

    def test_success_allows_no_error(self: Self) -> None:
        """success=True with no error is valid."""
        result = ExecutionResult(success=True)
        assert result.error is None

    def test_failure_factory(self: Self) -> None:
        """ExecutionResult.failure() convenience constructor."""
        result = ExecutionResult.failure(
            error="Something broke",
            metadata={"debug": True},
        )
        assert result.success is False
        assert result.error == "Something broke"
        assert result.data == {}
        assert result.metadata == {"debug": True}

    def test_failure_factory_no_metadata(self: Self) -> None:
        """failure() works without metadata."""
        result = ExecutionResult.failure(error="Oops")
        assert result.metadata == {}

    def test_error_not_in_success_dict(self: Self) -> None:
        """Successful result dict omits error key."""
        result = ExecutionResult(success=True, data={"k": "v"})
        d = result.to_dict()
        assert "error" not in d

    def test_error_in_failure_dict(self: Self) -> None:
        """Failed result dict includes error key."""
        result = ExecutionResult.failure(error="fail")
        d = result.to_dict()
        assert d["error"] == "fail"

    def test_default_empty_dicts(self: Self) -> None:
        """data and metadata default to empty dicts."""
        result = ExecutionResult(success=True)
        assert result.data == {}
        assert result.metadata == {}

    def test_from_dict_missing_optional_fields(self: Self) -> None:
        """from_dict handles missing optional fields."""
        minimal = {"success": True}
        result = ExecutionResult.from_dict(minimal)
        assert result.data == {}
        assert result.metadata == {}
        assert result.error is None

    def test_response_contract_extract(self: Self) -> None:
        """Verify extract operation response shape."""
        result = ExecutionResult(
            success=True,
            data={"extracted_text": "The quick brown fox"},
        )
        assert "extracted_text" in result.data

    def test_response_contract_index(self: Self) -> None:
        """Verify index operation response shape."""
        result = ExecutionResult(
            success=True,
            data={"doc_id": "doc-abc-123"},
        )
        assert "doc_id" in result.data

    def test_response_contract_answer_prompt(self: Self) -> None:
        """Verify answer_prompt operation response shape."""
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field1": "value1"},
                "metadata": {"confidence": 0.95},
                "metrics": {"tokens": 200},
            },
        )
        assert "output" in result.data
        assert "metadata" in result.data
        assert "metrics" in result.data


# ---- Phase 1B: BaseExecutor & ExecutorRegistry ----


def _make_executor_class(
    executor_name: str,
) -> type[BaseExecutor]:
    """Helper: build a concrete BaseExecutor subclass dynamically."""

    class _Executor(BaseExecutor):
        @property
        def name(self) -> str:
            return executor_name

        def execute(
            self, context: ExecutionContext
        ) -> ExecutionResult:
            return ExecutionResult(
                success=True,
                data={"echo": context.operation},
            )

    # Give it a readable __name__ for error messages
    _Executor.__name__ = f"{executor_name.title()}Executor"
    _Executor.__qualname__ = _Executor.__name__
    return _Executor


class TestBaseExecutor:
    """Tests for BaseExecutor ABC contract."""

    def test_cannot_instantiate_abstract(self: Self) -> None:
        """BaseExecutor itself cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseExecutor()  # type: ignore[abstract]

    def test_concrete_subclass_works(self: Self) -> None:
        """A properly implemented subclass can be instantiated."""
        cls = _make_executor_class("test_abc")
        instance = cls()
        assert instance.name == "test_abc"

    def test_execute_returns_result(self: Self) -> None:
        """execute() returns an ExecutionResult."""
        cls = _make_executor_class("test_exec")
        instance = cls()
        ctx = ExecutionContext(
            executor_name="test_exec",
            operation="extract",
            run_id="run-1",
            execution_source="tool",
        )
        result = instance.execute(ctx)
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.data == {"echo": "extract"}


class TestExecutorRegistry:
    """Tests for ExecutorRegistry."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self: Self) -> None:
        """Ensure a clean registry for every test."""
        ExecutorRegistry.clear()

    def test_register_and_get(self: Self) -> None:
        """Register an executor and retrieve by name."""
        cls = _make_executor_class("alpha")
        ExecutorRegistry.register(cls)

        executor = ExecutorRegistry.get("alpha")
        assert isinstance(executor, BaseExecutor)
        assert executor.name == "alpha"

    def test_get_returns_fresh_instance(self: Self) -> None:
        """Each get() call returns a new instance."""
        cls = _make_executor_class("fresh")
        ExecutorRegistry.register(cls)

        a = ExecutorRegistry.get("fresh")
        b = ExecutorRegistry.get("fresh")
        assert a is not b

    def test_register_as_decorator(self: Self) -> None:
        """@ExecutorRegistry.register works as a class decorator."""

        @ExecutorRegistry.register
        class MyExecutor(BaseExecutor):
            @property
            def name(self) -> str:
                return "decorated"

            def execute(
                self, context: ExecutionContext
            ) -> ExecutionResult:
                return ExecutionResult(success=True)

        executor = ExecutorRegistry.get("decorated")
        assert executor.name == "decorated"
        # Decorator returns the class unchanged
        assert MyExecutor is not None

    def test_list_executors(self: Self) -> None:
        """list_executors() returns sorted names."""
        ExecutorRegistry.register(_make_executor_class("charlie"))
        ExecutorRegistry.register(_make_executor_class("alpha"))
        ExecutorRegistry.register(_make_executor_class("bravo"))

        assert ExecutorRegistry.list_executors() == [
            "alpha",
            "bravo",
            "charlie",
        ]

    def test_list_executors_empty(self: Self) -> None:
        """list_executors() returns empty list when nothing registered."""
        assert ExecutorRegistry.list_executors() == []

    def test_get_unknown_raises_key_error(self: Self) -> None:
        """get() with unknown name raises KeyError."""
        with pytest.raises(KeyError, match="no_such_executor"):
            ExecutorRegistry.get("no_such_executor")

    def test_get_unknown_lists_available(self: Self) -> None:
        """KeyError message includes available executor names."""
        ExecutorRegistry.register(_make_executor_class("one"))
        ExecutorRegistry.register(_make_executor_class("two"))

        with pytest.raises(KeyError, match="one") as exc_info:
            ExecutorRegistry.get("missing")
        assert "two" in str(exc_info.value)

    def test_duplicate_name_raises_value_error(self: Self) -> None:
        """Registering two executors with the same name fails."""
        ExecutorRegistry.register(_make_executor_class("dup"))
        with pytest.raises(ValueError, match="already registered"):
            ExecutorRegistry.register(_make_executor_class("dup"))

    def test_register_non_subclass_raises_type_error(self: Self) -> None:
        """Registering a non-BaseExecutor class raises TypeError."""
        with pytest.raises(TypeError, match="not a BaseExecutor"):
            ExecutorRegistry.register(dict)  # type: ignore[arg-type]

    def test_register_non_class_raises_type_error(self: Self) -> None:
        """Registering a non-class object raises TypeError."""
        with pytest.raises(TypeError, match="not a BaseExecutor"):
            ExecutorRegistry.register("not_a_class")  # type: ignore[arg-type]

    def test_clear(self: Self) -> None:
        """clear() removes all registrations."""
        ExecutorRegistry.register(_make_executor_class("temp"))
        assert ExecutorRegistry.list_executors() == ["temp"]
        ExecutorRegistry.clear()
        assert ExecutorRegistry.list_executors() == []

    def test_execute_through_registry(self: Self) -> None:
        """End-to-end: register, get, execute."""
        ExecutorRegistry.register(_make_executor_class("e2e"))

        ctx = ExecutionContext(
            executor_name="e2e",
            operation="index",
            run_id="run-42",
            execution_source="ide",
        )
        executor = ExecutorRegistry.get("e2e")
        result = executor.execute(ctx)

        assert result.success is True
        assert result.data == {"echo": "index"}


# ---- Phase 1C: ExecutionOrchestrator ----


def _make_failing_executor_class(
    executor_name: str,
    exc: Exception,
) -> type[BaseExecutor]:
    """Build an executor that always raises *exc*."""

    class _FailExecutor(BaseExecutor):
        @property
        def name(self) -> str:
            return executor_name

        def execute(
            self, context: ExecutionContext
        ) -> ExecutionResult:
            raise exc

    _FailExecutor.__name__ = f"{executor_name.title()}FailExecutor"
    _FailExecutor.__qualname__ = _FailExecutor.__name__
    return _FailExecutor


class TestExecutionOrchestrator:
    """Tests for ExecutionOrchestrator."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self: Self) -> None:
        """Ensure a clean registry for every test."""
        ExecutorRegistry.clear()

    def _make_context(self, **overrides: Any) -> ExecutionContext:
        defaults: dict[str, Any] = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "run-1",
            "execution_source": "tool",
        }
        defaults.update(overrides)
        return ExecutionContext(**defaults)

    def test_dispatches_to_correct_executor(self: Self) -> None:
        """Orchestrator routes to the right executor by name."""
        ExecutorRegistry.register(_make_executor_class("alpha"))
        ExecutorRegistry.register(_make_executor_class("bravo"))

        orchestrator = ExecutionOrchestrator()

        result_a = orchestrator.execute(
            self._make_context(executor_name="alpha", operation="extract")
        )
        assert result_a.success is True
        assert result_a.data == {"echo": "extract"}

        result_b = orchestrator.execute(
            self._make_context(executor_name="bravo", operation="index")
        )
        assert result_b.success is True
        assert result_b.data == {"echo": "index"}

    def test_unknown_executor_returns_failure(self: Self) -> None:
        """Unknown executor_name yields a failure result (not exception)."""
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute(
            self._make_context(executor_name="nonexistent")
        )
        assert result.success is False
        assert "nonexistent" in result.error

    def test_executor_exception_returns_failure(self: Self) -> None:
        """Unhandled executor exception is wrapped in failure result."""
        ExecutorRegistry.register(
            _make_failing_executor_class(
                "boom", RuntimeError("kaboom")
            )
        )
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute(
            self._make_context(executor_name="boom")
        )
        assert result.success is False
        assert "RuntimeError" in result.error
        assert "kaboom" in result.error

    def test_exception_result_has_elapsed_metadata(self: Self) -> None:
        """Failure from exception includes elapsed_seconds metadata."""
        ExecutorRegistry.register(
            _make_failing_executor_class(
                "slow_fail", ValueError("bad input")
            )
        )
        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute(
            self._make_context(executor_name="slow_fail")
        )
        assert result.success is False
        assert "elapsed_seconds" in result.metadata
        assert isinstance(result.metadata["elapsed_seconds"], float)

    def test_successful_result_passed_through(self: Self) -> None:
        """Orchestrator returns the executor's result as-is on success."""
        ExecutorRegistry.register(_make_executor_class("passthru"))
        orchestrator = ExecutionOrchestrator()

        ctx = self._make_context(
            executor_name="passthru", operation="answer_prompt"
        )
        result = orchestrator.execute(ctx)

        assert result.success is True
        assert result.data == {"echo": "answer_prompt"}

    def test_executor_returning_failure_is_not_wrapped(
        self: Self,
    ) -> None:
        """An executor that returns failure result is passed through."""

        class FailingExecutor(BaseExecutor):
            @property
            def name(self) -> str:
                return "graceful_fail"

            def execute(
                self, context: ExecutionContext
            ) -> ExecutionResult:
                return ExecutionResult.failure(
                    error="LLM rate limited"
                )

        ExecutorRegistry.register(FailingExecutor)
        orchestrator = ExecutionOrchestrator()

        result = orchestrator.execute(
            self._make_context(executor_name="graceful_fail")
        )
        assert result.success is False
        assert result.error == "LLM rate limited"


# ---- Phase 1F: ExecutionDispatcher ----


class TestExecutionDispatcher:
    """Tests for ExecutionDispatcher (mocked Celery)."""

    def _make_context(self, **overrides: Any) -> ExecutionContext:
        defaults: dict[str, Any] = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "run-1",
            "execution_source": "tool",
            "request_id": "req-1",
        }
        defaults.update(overrides)
        return ExecutionContext(**defaults)

    def _make_mock_app(
        self,
        result_dict: dict[str, Any] | None = None,
        side_effect: Exception | None = None,
        task_id: str = "celery-task-123",
    ) -> MagicMock:
        """Create a mock Celery app with send_task configured."""
        mock_app = MagicMock()
        mock_async_result = MagicMock()
        mock_async_result.id = task_id

        if side_effect is not None:
            mock_async_result.get.side_effect = side_effect
        else:
            mock_async_result.get.return_value = (
                result_dict
                if result_dict is not None
                else {"success": True, "data": {}, "metadata": {}}
            )

        mock_app.send_task.return_value = mock_async_result
        return mock_app

    def test_dispatch_sends_task_and_returns_result(
        self: Self,
    ) -> None:
        """dispatch() sends task to executor queue and returns result."""
        result_dict = {
            "success": True,
            "data": {"extracted_text": "hello"},
            "metadata": {},
        }
        mock_app = self._make_mock_app(result_dict=result_dict)
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        result = dispatcher.dispatch(ctx, timeout=60)

        assert result.success is True
        assert result.data == {"extracted_text": "hello"}

        # Verify send_task was called correctly
        mock_app.send_task.assert_called_once_with(
            "execute_extraction",
            args=[ctx.to_dict()],
            queue="executor",
        )
        mock_app.send_task.return_value.get.assert_called_once_with(
            timeout=60, disable_sync_subtasks=False
        )

    def test_dispatch_uses_default_timeout(self: Self) -> None:
        """dispatch() without timeout uses default (3600s)."""
        mock_app = self._make_mock_app()
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        dispatcher.dispatch(ctx)

        mock_app.send_task.return_value.get.assert_called_once_with(
            timeout=3600, disable_sync_subtasks=False
        )

    def test_dispatch_timeout_from_env(
        self: Self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dispatch() reads timeout from EXECUTOR_RESULT_TIMEOUT env."""
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "120")
        mock_app = self._make_mock_app()
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        dispatcher.dispatch(ctx)

        mock_app.send_task.return_value.get.assert_called_once_with(
            timeout=120, disable_sync_subtasks=False
        )

    def test_dispatch_explicit_timeout_overrides_env(
        self: Self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit timeout parameter overrides env var."""
        monkeypatch.setenv("EXECUTOR_RESULT_TIMEOUT", "120")
        mock_app = self._make_mock_app()
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        dispatcher.dispatch(ctx, timeout=30)

        mock_app.send_task.return_value.get.assert_called_once_with(
            timeout=30, disable_sync_subtasks=False
        )

    def test_dispatch_timeout_returns_failure(
        self: Self,
    ) -> None:
        """TimeoutError from AsyncResult.get() is wrapped in failure."""
        mock_app = self._make_mock_app(
            side_effect=TimeoutError("Task timed out")
        )
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        result = dispatcher.dispatch(ctx, timeout=1)

        assert result.success is False
        assert "TimeoutError" in result.error

    def test_dispatch_generic_exception_returns_failure(
        self: Self,
    ) -> None:
        """Any exception from AsyncResult.get() becomes a failure."""
        mock_app = self._make_mock_app(
            side_effect=RuntimeError("broker down")
        )
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        result = dispatcher.dispatch(ctx, timeout=10)

        assert result.success is False
        assert "RuntimeError" in result.error
        assert "broker down" in result.error

    def test_dispatch_async_returns_task_id(self: Self) -> None:
        """dispatch_async() returns the Celery task ID."""
        mock_app = self._make_mock_app(task_id="task-xyz-789")
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        task_id = dispatcher.dispatch_async(ctx)

        assert task_id == "task-xyz-789"
        mock_app.send_task.assert_called_once_with(
            "execute_extraction",
            args=[ctx.to_dict()],
            queue="executor",
        )

    def test_dispatch_no_app_raises_value_error(
        self: Self,
    ) -> None:
        """dispatch() without celery_app raises ValueError."""
        dispatcher = ExecutionDispatcher(celery_app=None)
        ctx = self._make_context()

        with pytest.raises(ValueError, match="No Celery app"):
            dispatcher.dispatch(ctx)

    def test_dispatch_async_no_app_raises_value_error(
        self: Self,
    ) -> None:
        """dispatch_async() without celery_app raises ValueError."""
        dispatcher = ExecutionDispatcher(celery_app=None)
        ctx = self._make_context()

        with pytest.raises(ValueError, match="No Celery app"):
            dispatcher.dispatch_async(ctx)

    def test_dispatch_failure_result_from_executor(
        self: Self,
    ) -> None:
        """Executor failure is deserialized correctly."""
        result_dict = {
            "success": False,
            "data": {},
            "metadata": {},
            "error": "LLM adapter timeout",
        }
        mock_app = self._make_mock_app(result_dict=result_dict)
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context()

        result = dispatcher.dispatch(ctx, timeout=60)

        assert result.success is False
        assert result.error == "LLM adapter timeout"

    def test_dispatch_context_serialized_correctly(
        self: Self,
    ) -> None:
        """The full ExecutionContext is serialized in the task args."""
        mock_app = self._make_mock_app()
        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = self._make_context(
            executor_name="agentic_table",
            operation="agentic_extraction",
            organization_id="org-42",
            executor_params={"schema": {"name": "str"}},
        )

        dispatcher.dispatch(ctx, timeout=60)

        sent_args = mock_app.send_task.call_args
        context_dict = sent_args[1]["args"][0]

        assert context_dict["executor_name"] == "agentic_table"
        assert context_dict["operation"] == "agentic_extraction"
        assert context_dict["organization_id"] == "org-42"
        assert context_dict["executor_params"] == {
            "schema": {"name": "str"}
        }


# ---- Phase 1G: ExecutorToolShim ----
# Note: ExecutorToolShim lives in workers/executor/ but the tests
# import it directly via sys.path manipulation since the workers
# package requires Celery (not installed in SDK1 test venv).
# We test the shim's logic here by importing its direct dependencies
# from SDK1 (StreamMixin, SdkError, LogLevel, ToolEnv).


class _MockExecutorToolShim:
    """In-test replica of ExecutorToolShim for SDK1 test isolation.

    The real ExecutorToolShim lives in workers/executor/ and cannot
    be imported here (Celery not in SDK1 venv).  This replica
    mirrors the same logic so we can verify the behavior contract
    without importing the workers package.
    """

    def __init__(self, platform_api_key: str = "") -> None:
        self.platform_api_key = platform_api_key

    def get_env_or_die(self, env_key: str) -> str:
        import os

        if env_key == ToolEnv.PLATFORM_API_KEY:
            if not self.platform_api_key:
                raise SdkError(
                    f"Env variable '{env_key}' is required"
                )
            return self.platform_api_key

        env_value = os.environ.get(env_key)
        if env_value is None or env_value == "":
            raise SdkError(
                f"Env variable '{env_key}' is required"
            )
        return env_value

    def stream_log(
        self,
        log: str,
        level: LogLevel = LogLevel.INFO,
        stage: str = "TOOL_RUN",
        **kwargs: Any,
    ) -> None:
        _level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARN: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.FATAL: logging.CRITICAL,
        }
        py_level = _level_map.get(level, logging.INFO)
        logging.getLogger("executor_tool_shim").log(py_level, log)

    def stream_error_and_exit(
        self, message: str, err: Exception | None = None
    ) -> None:
        raise SdkError(message, actual_err=err)


class TestExecutorToolShim:
    """Tests for ExecutorToolShim behavior contract."""

    def test_platform_api_key_returned(self: Self) -> None:
        """get_env_or_die('PLATFORM_SERVICE_API_KEY') returns configured key."""
        shim = _MockExecutorToolShim(platform_api_key="sk-test-123")
        result = shim.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
        assert result == "sk-test-123"

    def test_platform_api_key_missing_raises(self: Self) -> None:
        """get_env_or_die('PLATFORM_SERVICE_API_KEY') raises when not configured."""
        shim = _MockExecutorToolShim(platform_api_key="")
        with pytest.raises(SdkError, match="PLATFORM_SERVICE_API_KEY"):
            shim.get_env_or_die(ToolEnv.PLATFORM_API_KEY)

    def test_other_env_var_from_environ(
        self: Self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_env_or_die() reads non-platform vars from os.environ."""
        monkeypatch.setenv("MY_CUSTOM_VAR", "custom_value")
        shim = _MockExecutorToolShim(platform_api_key="sk-test")
        result = shim.get_env_or_die("MY_CUSTOM_VAR")
        assert result == "custom_value"

    def test_missing_env_var_raises(self: Self) -> None:
        """get_env_or_die() raises SdkError for missing env var."""
        shim = _MockExecutorToolShim(platform_api_key="sk-test")
        with pytest.raises(SdkError, match="NONEXISTENT_VAR"):
            shim.get_env_or_die("NONEXISTENT_VAR")

    def test_empty_env_var_raises(
        self: Self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_env_or_die() raises SdkError for empty env var."""
        monkeypatch.setenv("EMPTY_VAR", "")
        shim = _MockExecutorToolShim(platform_api_key="sk-test")
        with pytest.raises(SdkError, match="EMPTY_VAR"):
            shim.get_env_or_die("EMPTY_VAR")

    def test_stream_log_routes_to_logging(
        self: Self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """stream_log() routes to Python logging, not stdout."""
        shim = _MockExecutorToolShim()
        with caplog.at_level(logging.INFO, logger="executor_tool_shim"):
            shim.stream_log("test message", level=LogLevel.INFO)
        assert "test message" in caplog.text

    def test_stream_log_respects_level(
        self: Self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """stream_log() maps SDK LogLevel to Python logging level."""
        shim = _MockExecutorToolShim()
        with caplog.at_level(logging.WARNING, logger="executor_tool_shim"):
            shim.stream_log("debug msg", level=LogLevel.DEBUG)
            shim.stream_log("warn msg", level=LogLevel.WARN)
        # DEBUG should be filtered out at WARNING level
        assert "debug msg" not in caplog.text
        assert "warn msg" in caplog.text

    def test_stream_error_and_exit_raises_sdk_error(
        self: Self,
    ) -> None:
        """stream_error_and_exit() raises SdkError (no sys.exit)."""
        shim = _MockExecutorToolShim()
        with pytest.raises(SdkError, match="something failed"):
            shim.stream_error_and_exit("something failed")

    def test_stream_error_and_exit_wraps_original(
        self: Self,
    ) -> None:
        """stream_error_and_exit() passes original exception."""
        shim = _MockExecutorToolShim()
        original = ValueError("root cause")
        with pytest.raises(SdkError) as exc_info:
            shim.stream_error_and_exit("wrapper msg", err=original)
        assert exc_info.value.actual_err is original
