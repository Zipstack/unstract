"""Integration tests for Celery backend.

These tests require Redis to be running and Celery to be installed.
Run with: pytest tests/integration/test_celery_backend.py -m integration
"""

import pytest
import time
from unittest.mock import patch

from task_abstraction.backends.celery import CeleryBackend
from task_abstraction.models import BackendConfig


@pytest.mark.integration
class TestCeleryBackendIntegration:
    """Integration tests for Celery backend."""

    @pytest.fixture
    def celery_config(self):
        """Create test Celery configuration."""
        return BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            },
            worker_config={
                "concurrency": 2,
                "max_tasks_per_child": 10,
            }
        )

    @pytest.fixture
    def celery_backend(self, celery_config):
        """Create Celery backend instance."""
        try:
            backend = CeleryBackend(celery_config)
            yield backend
        except ImportError:
            pytest.skip("Celery not installed")

    def test_backend_creation(self, celery_backend):
        """Test that Celery backend can be created."""
        assert celery_backend.backend_type == "celery"
        assert celery_backend.config.backend_type == "celery"

    def test_task_registration(self, celery_backend):
        """Test registering tasks with Celery backend."""
        @celery_backend.register_task
        def add(x, y):
            return x + y

        assert "add" in celery_backend._tasks
        celery_task = celery_backend._tasks["add"]

        # Test that the Celery task can be called directly
        result = celery_task(2, 3)
        assert result == 5

    def test_task_registration_with_name(self, celery_backend):
        """Test registering task with custom name."""
        def multiply(x, y):
            return x * y

        celery_backend.register_task(multiply, name="custom_multiply")

        assert "custom_multiply" in celery_backend._tasks
        assert celery_backend._tasks["custom_multiply"](4, 5) == 20

    def test_task_submission(self, celery_backend):
        """Test submitting tasks for execution."""
        @celery_backend.register_task
        def subtract(x, y):
            return x - y

        task_id = celery_backend.submit("subtract", 10, 3)

        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_task_result_retrieval(self, celery_backend):
        """Test retrieving task results."""
        @celery_backend.register_task
        def divide(x, y):
            return x / y

        task_id = celery_backend.submit("divide", 10, 2)

        # Wait a bit for the task to complete (since we don't have a worker running)
        # In a real test, you'd have a test worker or use eager mode
        result = celery_backend.get_result(task_id)

        assert result.task_id == task_id
        # Note: Without a worker running, the task will be in PENDING state

    def test_submit_unregistered_task(self, celery_backend):
        """Test submitting an unregistered task raises error."""
        with pytest.raises(ValueError, match="Task 'nonexistent' not registered"):
            celery_backend.submit("nonexistent", 1, 2)

    @patch('celery.app.Celery.control')
    def test_connection_check(self, mock_control, celery_backend):
        """Test backend connection checking."""
        # Mock successful connection
        mock_inspect = mock_control.inspect.return_value
        mock_inspect.stats.return_value = {"worker1": {"pool": {"max-concurrency": 4}}}

        assert celery_backend.is_connected()

        # Mock connection failure
        mock_inspect.stats.side_effect = Exception("Connection failed")
        assert not celery_backend.is_connected()

    def test_default_configuration(self):
        """Test Celery backend with default configuration."""
        try:
            backend = CeleryBackend()
            assert backend.config.backend_type == "celery"
            assert backend.config.connection_params["broker_url"] == "redis://localhost:6379/0"
        except ImportError:
            pytest.skip("Celery not installed")

    def test_eager_mode_execution(self):
        """Test task execution in eager mode (synchronous)."""
        config = BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            }
        )

        try:
            backend = CeleryBackend(config)
            # Configure eager mode for testing
            backend.app.conf.task_always_eager = True
            backend.app.conf.task_eager_propagates = True

            @backend.register_task
            def square(x):
                return x * x

            task_id = backend.submit("square", 5)
            result = backend.get_result(task_id)

            # In eager mode, the task executes immediately
            assert result.status == "completed"
            assert result.result == 25

        except ImportError:
            pytest.skip("Celery not installed")


@pytest.mark.integration
@pytest.mark.slow
class TestCeleryWorkerIntegration:
    """Integration tests that require a Celery worker process."""

    def test_worker_startup_simulation(self):
        """Test worker startup configuration (without actually starting)."""
        config = BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            },
            worker_config={
                "concurrency": 4,
                "max_tasks_per_child": 100,
            }
        )

        try:
            backend = CeleryBackend(config)

            # Test that worker configuration is applied
            assert backend.app.conf.broker_url == "redis://localhost:6379/0"
            assert backend.app.conf.result_backend == "redis://localhost:6379/0"

            # Register a task
            @backend.register_task
            def test_task():
                return "worker test"

            assert "test_task" in backend._tasks

        except ImportError:
            pytest.skip("Celery not installed")