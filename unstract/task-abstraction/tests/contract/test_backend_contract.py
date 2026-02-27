"""Contract tests for TaskBackend interface compliance.

These tests verify that all backend implementations properly implement
the TaskBackend interface contract.
"""

from abc import ABC

import pytest
from task_abstraction.base import TaskBackend
from task_abstraction.models import BackendConfig


class BackendContractTestBase(ABC):
    """Base contract test class that all backends must satisfy."""

    @pytest.fixture
    def backend_config(self):
        """Override in subclasses to provide backend-specific config."""
        raise NotImplementedError("Subclasses must provide backend_config fixture")

    @pytest.fixture
    def backend(self, backend_config):
        """Override in subclasses to create backend instance."""
        raise NotImplementedError("Subclasses must provide backend fixture")

    def test_backend_is_taskbackend_instance(self, backend):
        """Test that backend is an instance of TaskBackend."""
        assert isinstance(backend, TaskBackend)

    def test_backend_has_required_methods(self, backend):
        """Test that backend implements all required methods."""
        required_methods = ["register_task", "submit", "get_result", "run_worker"]
        for method_name in required_methods:
            assert hasattr(backend, method_name), f"Missing method: {method_name}"
            assert callable(
                getattr(backend, method_name)
            ), f"Method not callable: {method_name}"

    def test_backend_has_required_properties(self, backend):
        """Test that backend has required properties."""
        assert hasattr(backend, "backend_type")
        assert isinstance(backend.backend_type, str)
        assert len(backend.backend_type) > 0

    def test_backend_config_stored(self, backend, backend_config):
        """Test that backend stores configuration."""
        assert hasattr(backend, "config")
        # Config might be None for some backends
        if backend.config is not None:
            assert isinstance(backend.config, BackendConfig)

    def test_tasks_registry_exists(self, backend):
        """Test that backend maintains a tasks registry."""
        assert hasattr(backend, "_tasks")
        assert isinstance(backend._tasks, dict)

    def test_register_task_basic(self, backend):
        """Test basic task registration."""

        def sample_task(x):
            return x * 2

        result = backend.register_task(sample_task)

        # Should return the function (for decorator usage)
        assert result == sample_task

        # Should store in tasks registry
        assert "sample_task" in backend._tasks
        assert backend._tasks["sample_task"] == sample_task

    def test_register_task_with_custom_name(self, backend):
        """Test task registration with custom name."""

        def another_task(x):
            return x + 1

        backend.register_task(another_task, name="custom_name")

        assert "custom_name" in backend._tasks
        assert backend._tasks["custom_name"] == another_task

    def test_register_task_as_decorator(self, backend):
        """Test using register_task as a decorator."""

        @backend.register_task
        def decorated_task(x):
            return x**2

        assert "decorated_task" in backend._tasks
        assert decorated_task(5) == 25  # Function should still work

    def test_submit_requires_registered_task(self, backend):
        """Test that submit() requires task to be registered."""
        with pytest.raises(ValueError, match="not registered"):
            backend.submit("nonexistent_task", 1, 2, 3)

    def test_backend_type_property_format(self, backend):
        """Test backend_type property format."""
        backend_type = backend.backend_type
        assert isinstance(backend_type, str)
        assert backend_type.islower()  # Should be lowercase
        assert " " not in backend_type  # No spaces
        # Verify consistency with backend config if available
        expected_type = getattr(getattr(backend, "config", None), "backend_type", None)
        if expected_type:
            assert backend_type == expected_type

    def test_repr_contains_backend_info(self, backend):
        """Test that __repr__ contains useful information."""
        repr_str = repr(backend)
        assert isinstance(repr_str, str)
        assert backend.backend_type in repr_str.lower()


class MockTaskBackendForContract(TaskBackend):
    """Mock implementation for contract testing."""

    def __init__(self, config=None):
        super().__init__(config)
        self.submitted_tasks = []

    def register_task(self, fn, name=None):
        task_name = name or fn.__name__
        self._tasks[task_name] = fn
        return fn

    def submit(self, name, *args, **kwargs):
        if name not in self._tasks:
            raise ValueError(f"Task '{name}' not registered")

        task_id = f"mock-{len(self.submitted_tasks)}"
        self.submitted_tasks.append(
            {"task_id": task_id, "name": name, "args": args, "kwargs": kwargs}
        )
        return task_id

    def get_result(self, task_id):
        from task_abstraction.models import TaskResult

        # Find the submitted task
        for task in self.submitted_tasks:
            if task["task_id"] == task_id:
                # Execute the task synchronously for testing
                fn = self._tasks[task["name"]]
                try:
                    result = fn(*task["args"], **task["kwargs"])
                    return TaskResult(
                        task_id=task_id,
                        task_name=task["name"],
                        status="completed",
                        result=result,
                    )
                except Exception as e:
                    return TaskResult(
                        task_id=task_id,
                        task_name=task["name"],
                        status="failed",
                        error=str(e),
                    )

        return TaskResult(
            task_id=task_id, task_name="unknown", status="failed", error="Task not found"
        )

    def run_worker(self):
        # Mock implementation
        pass


class TestMockBackendContract(BackendContractTestBase):
    """Test mock backend against the contract."""

    @pytest.fixture
    def backend_config(self):
        return BackendConfig(backend_type="mock", connection_params={"test": "value"})

    @pytest.fixture
    def backend(self, backend_config):
        return MockTaskBackendForContract(backend_config)

    def test_submit_and_get_result_workflow(self, backend):
        """Test complete submit -> get_result workflow."""

        @backend.register_task
        def add_numbers(a, b):
            return a + b

        # Submit task
        task_id = backend.submit("add_numbers", 5, 3)
        assert isinstance(task_id, str)

        # Get result
        result = backend.get_result(task_id)
        assert result.task_id == task_id
        assert result.task_name == "add_numbers"
        assert result.status == "completed"
        assert result.result == 8

    def test_failed_task_result(self, backend):
        """Test getting result for failed task."""

        @backend.register_task
        def failing_task():
            raise Exception("Task failed")

        task_id = backend.submit("failing_task")
        result = backend.get_result(task_id)

        assert result.status == "failed"
        assert "Task failed" in result.error


class TestRealBackendContracts:
    """Test real backend implementations against contracts."""

    def test_celery_backend_contract(self):
        """Test Celery backend contract compliance."""
        try:
            from task_abstraction.backends.celery import CeleryBackend

            config = BackendConfig(
                backend_type="celery",
                connection_params={"broker_url": "redis://localhost:6379/0"},
            )

            backend = CeleryBackend(config)

            # Run basic contract tests
            assert isinstance(backend, TaskBackend)
            assert backend.backend_type == "celery"
            assert hasattr(backend, "_tasks")

        except ImportError:
            pytest.skip("Celery not installed")

    def test_hatchet_backend_contract(self):
        """Test Hatchet backend contract compliance."""
        try:
            from task_abstraction.backends.hatchet import HatchetBackend

            config = BackendConfig(
                backend_type="hatchet",
                connection_params={
                    "token": "test-token",
                    "server_url": "https://app.hatchet.run",
                },
            )

            backend = HatchetBackend(config)

            # Run basic contract tests
            assert isinstance(backend, TaskBackend)
            assert backend.backend_type == "hatchet"
            assert hasattr(backend, "_tasks")

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    def test_temporal_backend_contract(self):
        """Test Temporal backend contract compliance."""
        try:
            from task_abstraction.backends.temporal import TemporalBackend

            config = BackendConfig(
                backend_type="temporal",
                connection_params={
                    "host": "localhost",
                    "port": 7233,
                    "namespace": "default",
                    "task_queue": "test-queue",
                },
            )

            backend = TemporalBackend(config)

            # Run basic contract tests
            assert isinstance(backend, TaskBackend)
            assert backend.backend_type == "temporal"
            assert hasattr(backend, "_tasks")

        except ImportError:
            pytest.skip("Temporal SDK not installed")
