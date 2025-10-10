#!/usr/bin/env python3
"""Simple test runner for task abstraction library.

This script runs the core tests without requiring pytest installation.
For full test suite, use: pytest tests/
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_test(test_name, test_func):
    """Run a single test function."""
    try:
        test_func()
        print(f"✓ {test_name}")
        return True
    except Exception as e:
        print(f"✗ {test_name}: {e}")
        return False


def test_models():
    """Test core models."""
    from datetime import datetime

    from task_abstraction.models import BackendConfig, TaskResult

    # Test TaskResult
    result = TaskResult("test-123", "test_task", "completed", result=42)
    assert result.is_completed
    assert result.result == 42

    # Test duration calculation
    start = datetime(2023, 1, 1, 12, 0, 0)
    end = datetime(2023, 1, 1, 12, 0, 5)
    timed_result = TaskResult(
        "test", "test", "completed", started_at=start, completed_at=end
    )
    assert timed_result.duration == 5.0

    # Test BackendConfig
    config = BackendConfig("celery", {"broker_url": "redis://localhost:6379/0"})
    assert config.validate()

    invalid_config = BackendConfig("celery", {})
    assert not invalid_config.validate()


def test_base_interface():
    """Test TaskBackend base interface."""
    from task_abstraction.base import TaskBackend, task
    from task_abstraction.models import TaskResult

    class MockBackend(TaskBackend):
        def __init__(self, config=None):
            super().__init__(config)
            self.submitted = []

        def register_task(self, fn, name=None):
            task_name = name or fn.__name__
            self._tasks[task_name] = fn
            return fn

        def submit(self, name, *args, **kwargs):
            if name not in self._tasks:
                raise ValueError(f"Task '{name}' not registered")
            task_id = f"mock-{len(self.submitted)}"
            self.submitted.append(
                {"id": task_id, "name": name, "args": args, "kwargs": kwargs}
            )
            return task_id

        def get_result(self, task_id):
            for task in self.submitted:
                if task["id"] == task_id:
                    fn = self._tasks[task["name"]]
                    result = fn(*task["args"], **task["kwargs"])
                    return TaskResult(task_id, task["name"], "completed", result=result)
            return TaskResult(task_id, "unknown", "failed", error="Not found")

        def run_worker(self):
            pass

    # Test backend creation
    backend = MockBackend()
    assert backend.backend_type == "mock"

    # Test task registration
    @backend.register_task
    def add(x, y):
        return x + y

    assert "add" in backend._tasks

    # Test submission and results
    task_id = backend.submit("add", 2, 3)
    result = backend.get_result(task_id)
    assert result.is_completed
    assert result.result == 5

    # Test error handling
    try:
        backend.submit("nonexistent", 1, 2)
        pytest.fail("Should have raised ValueError")
    except ValueError:
        pass  # Expected

    # Test standalone decorator
    @task(backend, name="custom_multiply")
    def multiply(a, b):
        return a * b

    assert "custom_multiply" in backend._tasks
    assert multiply(3, 4) == 12


def test_factory():
    """Test backend factory."""
    from task_abstraction.config import get_default_config
    from task_abstraction.factory import get_available_backends

    # Test available backends
    backends = get_available_backends()
    assert isinstance(backends, list)
    assert len(backends) > 0

    # Test default configs
    for backend_type in ["celery", "temporal"]:
        config = get_default_config(backend_type)
        assert config.backend_type == backend_type
        assert config.validate()


def test_configuration():
    """Test configuration system."""

    from task_abstraction.config import get_default_config, load_config_from_env

    # Test environment loading with defaults
    with_env = load_config_from_env("celery")
    assert with_env.backend_type == "celery"
    assert with_env.validate()

    # Test default config generation
    default = get_default_config("temporal")
    assert default.backend_type == "temporal"
    assert default.validate()


def test_full_workflow():
    """Test complete workflow."""
    from task_abstraction import get_backend
    from task_abstraction.models import BackendConfig

    # Test with default config (no external dependencies)
    try:
        # This will fail because Celery isn't installed, but error handling should work
        get_backend("celery", use_env=False)
        pytest.fail("Should have failed due to missing Celery")
    except ImportError as e:
        assert "Celery" in str(e)

    # Test with BackendConfig object
    config = BackendConfig("celery", {"broker_url": "redis://localhost:6379/0"})
    try:
        get_backend(config=config)
        pytest.fail("Should have failed due to missing Celery")
    except ImportError:
        pass  # Expected


def main():
    """Run all tests."""
    print("Running task abstraction tests...\n")

    tests = [
        ("Models", test_models),
        ("Base Interface", test_base_interface),
        ("Factory", test_factory),
        ("Configuration", test_configuration),
        ("Full Workflow", test_full_workflow),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        if run_test(test_name, test_func):
            passed += 1

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
