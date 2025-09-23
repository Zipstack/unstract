"""Unit tests for TaskBackend base class."""

import pytest
from unittest.mock import Mock

from task_abstraction.base import TaskBackend, task
from task_abstraction.models import BackendConfig


class MockTaskBackend(TaskBackend):
    """Mock implementation of TaskBackend for testing."""

    def __init__(self, config=None):
        super().__init__(config)
        self.submitted_tasks = []
        self.task_results = {}

    def register_task(self, fn, name=None):
        task_name = name or fn.__name__
        self._tasks[task_name] = fn
        return fn

    def submit(self, name, *args, **kwargs):
        if name not in self._tasks:
            raise ValueError(f"Task '{name}' not registered")

        task_id = f"mock-{len(self.submitted_tasks)}"
        self.submitted_tasks.append({
            "task_id": task_id,
            "name": name,
            "args": args,
            "kwargs": kwargs
        })

        # Execute immediately for testing
        result = self._tasks[name](*args, **kwargs)
        self.task_results[task_id] = result

        return task_id

    def get_result(self, task_id):
        from task_abstraction.models import TaskResult

        if task_id in self.task_results:
            return TaskResult(
                task_id=task_id,
                task_name="test",
                status="completed",
                result=self.task_results[task_id]
            )
        else:
            return TaskResult(
                task_id=task_id,
                task_name="test",
                status="failed",
                error="Task not found"
            )

    def run_worker(self):
        # Mock implementation - just return
        pass


class TestTaskBackend:
    """Test TaskBackend abstract base class."""

    def test_backend_initialization(self):
        """Test TaskBackend initialization."""
        config = BackendConfig(
            backend_type="mock",
            connection_params={"test": "value"}
        )

        backend = MockTaskBackend(config)

        assert backend.config == config
        assert backend._tasks == {}
        assert backend.backend_type == "mocktaskbackend"

    def test_backend_initialization_no_config(self):
        """Test TaskBackend initialization without config."""
        backend = MockTaskBackend()
        assert backend.config is None
        assert backend._tasks == {}

    def test_register_task_basic(self):
        """Test basic task registration."""
        backend = MockTaskBackend()

        def add(x, y):
            return x + y

        registered_fn = backend.register_task(add)

        assert "add" in backend._tasks
        assert backend._tasks["add"] == add
        assert registered_fn == add

    def test_register_task_with_name(self):
        """Test task registration with custom name."""
        backend = MockTaskBackend()

        def add(x, y):
            return x + y

        backend.register_task(add, name="custom_add")

        assert "custom_add" in backend._tasks
        assert backend._tasks["custom_add"] == add

    def test_register_task_decorator(self):
        """Test task registration using decorator."""
        backend = MockTaskBackend()

        @backend.register_task
        def multiply(x, y):
            return x * y

        assert "multiply" in backend._tasks
        assert backend._tasks["multiply"](3, 4) == 12

    def test_submit_registered_task(self):
        """Test submitting a registered task."""
        backend = MockTaskBackend()

        @backend.register_task
        def add(x, y):
            return x + y

        task_id = backend.submit("add", 2, 3)

        assert len(backend.submitted_tasks) == 1
        assert backend.submitted_tasks[0]["name"] == "add"
        assert backend.submitted_tasks[0]["args"] == (2, 3)
        assert backend.task_results[task_id] == 5

    def test_submit_unregistered_task(self):
        """Test submitting an unregistered task raises error."""
        backend = MockTaskBackend()

        with pytest.raises(ValueError, match="Task 'nonexistent' not registered"):
            backend.submit("nonexistent", 1, 2)

    def test_submit_with_kwargs(self):
        """Test submitting task with keyword arguments."""
        backend = MockTaskBackend()

        @backend.register_task
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        task_id = backend.submit("greet", "Alice", greeting="Hi")

        assert backend.task_results[task_id] == "Hi, Alice!"

    def test_get_result_success(self):
        """Test getting result for successful task."""
        backend = MockTaskBackend()

        @backend.register_task
        def double(x):
            return x * 2

        task_id = backend.submit("double", 5)
        result = backend.get_result(task_id)

        assert result.task_id == task_id
        assert result.status == "completed"
        assert result.result == 10

    def test_get_result_not_found(self):
        """Test getting result for non-existent task."""
        backend = MockTaskBackend()

        result = backend.get_result("nonexistent-id")

        assert result.status == "failed"
        assert "Task not found" in result.error

    def test_backend_type_property(self):
        """Test backend_type property extraction."""
        backend = MockTaskBackend()
        assert backend.backend_type == "mocktaskbackend"

    def test_repr(self):
        """Test string representation of backend."""
        backend = MockTaskBackend()
        repr_str = repr(backend)
        assert "MockTaskBackend" in repr_str
        assert "type='mocktaskbackend'" in repr_str


class TestTaskDecorator:
    """Test the task decorator function."""

    def test_task_decorator(self):
        """Test task decorator function."""
        backend = MockTaskBackend()

        @task(backend)
        def subtract(x, y):
            return x - y

        assert "subtract" in backend._tasks
        assert backend._tasks["subtract"](10, 3) == 7

    def test_task_decorator_with_name(self):
        """Test task decorator with custom name."""
        backend = MockTaskBackend()

        @task(backend, name="custom_subtract")
        def subtract(x, y):
            return x - y

        assert "custom_subtract" in backend._tasks
        assert backend._tasks["custom_subtract"](10, 3) == 7

    def test_task_decorator_returns_original_function(self):
        """Test that decorator returns the original function."""
        backend = MockTaskBackend()

        def divide(x, y):
            return x / y

        decorated = task(backend)(divide)

        assert decorated == divide
        assert decorated(10, 2) == 5.0