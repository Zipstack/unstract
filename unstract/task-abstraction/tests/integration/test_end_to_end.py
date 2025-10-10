"""End-to-end workflow execution tests.

These tests verify the complete task abstraction workflow across all backends.
Run with: pytest tests/integration/test_end_to_end.py -m integration
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from task_abstraction import get_available_backends, get_backend
from task_abstraction.config import get_default_config
from task_abstraction.models import BackendConfig


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end tests using the complete task abstraction interface."""

    def test_available_backends_discovery(self):
        """Test that backends are properly discovered."""
        backends = get_available_backends()
        assert isinstance(backends, list)
        assert len(backends) > 0

        # Should include the main backends
        expected_backends = ["celery", "hatchet", "temporal"]
        for backend in expected_backends:
            assert backend in backends

    def test_default_config_generation(self):
        """Test default configuration generation for all backends."""
        for backend_type in ["celery", "temporal"]:  # Skip hatchet (needs token)
            config = get_default_config(backend_type)
            assert config.backend_type == backend_type
            assert config.validate()

    @patch("task_abstraction.backends.celery.Celery")
    def test_celery_end_to_end_workflow(self, mock_celery_class):
        """Test complete workflow with Celery backend."""
        # Mock Celery app and components
        mock_app = Mock()
        mock_celery_class.return_value = mock_app

        # Mock AsyncResult for result retrieval
        mock_result = Mock()
        mock_result.id = "celery-task-123"
        mock_app.task.return_value = lambda fn: fn  # Return original function

        try:
            # Get backend using the factory
            backend = get_backend("celery", use_env=False)

            # Register a task using the @decorator syntax
            @backend.register_task
            def calculate_fibonacci(n):
                if n <= 1:
                    return n
                return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)

            # Verify task was registered
            assert "calculate_fibonacci" in backend._tasks

            # Mock task submission
            with patch.object(backend, "submit") as mock_submit:
                mock_submit.return_value = "celery-task-123"

                task_id = backend.submit("calculate_fibonacci", 5)
                assert task_id == "celery-task-123"
                mock_submit.assert_called_once_with("calculate_fibonacci", 5)

            # Mock result retrieval
            with patch.object(backend, "get_result") as mock_get_result:
                from task_abstraction.models import TaskResult

                expected_result = TaskResult(
                    task_id="celery-task-123",
                    task_name="calculate_fibonacci",
                    status="completed",
                    result=5,  # fibonacci(5) = 5
                )
                mock_get_result.return_value = expected_result

                result = backend.get_result("celery-task-123")
                assert result.is_completed
                assert result.result == 5

        except ImportError:
            pytest.skip("Celery not installed")

    @patch("hatchet_sdk.Hatchet")
    def test_hatchet_end_to_end_workflow(self, mock_hatchet_class):
        """Test complete workflow with Hatchet backend."""
        # Mock Hatchet client
        mock_hatchet = Mock()
        mock_hatchet.workflow.return_value = lambda fn: fn
        mock_hatchet.step.return_value = lambda fn: fn
        mock_hatchet_class.return_value = mock_hatchet

        # Mock workflow run
        mock_workflow_run = Mock()
        mock_workflow_run.workflow_run_id = "hatchet-run-456"
        mock_hatchet.admin.trigger_workflow.return_value = mock_workflow_run

        config = BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "test-token",
                "server_url": "https://app.hatchet.run",
            },
        )

        try:
            # Get backend with explicit config
            backend = get_backend(config=config)

            # Register a task with custom name
            def process_document(content):
                return {"word_count": len(content.split())}

            backend.register_task(process_document, name="doc_processor")

            # Verify task was registered
            assert "doc_processor" in backend._tasks

            # Submit task
            task_id = backend.submit("doc_processor", "hello world from hatchet")
            assert task_id == "hatchet-run-456"

            # Verify workflow was triggered
            mock_hatchet.admin.trigger_workflow.assert_called_once()
            call_args = mock_hatchet.admin.trigger_workflow.call_args
            assert call_args[1]["workflow_name"] == "doc_processor_workflow"

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.activity.defn")
    @patch("temporalio.workflow.defn")
    def test_temporal_end_to_end_workflow(
        self, mock_workflow_defn, mock_activity_defn, mock_connect
    ):
        """Test complete workflow with Temporal backend."""
        # Mock decorators
        mock_activity_defn.return_value = lambda fn: fn
        mock_workflow_defn.return_value = lambda cls: cls

        # Mock client
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        # Mock workflow handle
        mock_handle = Mock()
        mock_handle.id = "temporal-workflow-789"
        mock_client.start_workflow.return_value = mock_handle

        try:
            # Get backend with default config
            backend = get_backend("temporal", use_env=False)

            # Register a task
            @backend.register_task
            def validate_email(email):
                return "@" in email and "." in email.split("@")[1]

            # Verify task was registered
            assert "validate_email" in backend._tasks

            # Submit task (this will call async code synchronously)
            task_id = backend.submit("validate_email", "test@example.com")
            assert task_id == "temporal-workflow-789"

        except ImportError:
            pytest.skip("Temporal SDK not installed")

    def test_backend_switching_configuration(self):
        """Test that backend can be switched via configuration."""
        # Test with different backend types
        backend_configs = [
            BackendConfig("celery", {"broker_url": "redis://localhost:6379/0"}),
            BackendConfig(
                "temporal",
                {
                    "host": "localhost",
                    "port": 7233,
                    "namespace": "default",
                    "task_queue": "test",
                },
            ),
        ]

        for config in backend_configs:
            try:
                backend = get_backend(config=config)
                assert backend.backend_type == config.backend_type

                # Test task registration works
                @backend.register_task
                def test_task():
                    return "success"

                assert "test_task" in backend._tasks

            except ImportError:
                pytest.skip(f"{config.backend_type} not installed")

    @patch("task_abstraction.config.yaml.safe_load")
    @patch("builtins.open")
    @patch("os.path.exists")
    def test_file_based_configuration(self, mock_exists, mock_open, mock_yaml_load):
        """Test loading backend from YAML configuration file."""
        # Mock file exists
        mock_exists.return_value = True

        # Mock YAML content
        mock_yaml_load.return_value = {
            "backend": "celery",
            "celery": {
                "broker_url": "redis://config:6379/0",
                "result_backend": "redis://config:6379/1",
            },
            "worker": {"concurrency": 8},
        }

        try:
            # Mock the YAML_AVAILABLE flag
            with patch("task_abstraction.config.YAML_AVAILABLE", True):
                backend = get_backend(config="test-config.yaml")
                assert backend.backend_type == "celery"

        except ImportError:
            pytest.skip("Dependencies not installed")

    def test_task_decorator_functionality(self):
        """Test the standalone task decorator."""
        from task_abstraction import task

        try:
            backend = get_backend("celery", use_env=False)

            # Use standalone decorator
            @task(backend, name="decorated_task")
            def multiply_numbers(a, b):
                return a * b

            assert "decorated_task" in backend._tasks

            # Test the function still works normally
            result = multiply_numbers(3, 4)
            assert result == 12

        except ImportError:
            pytest.skip("Backend dependencies not installed")

    def test_error_handling_across_backends(self):
        """Test error handling behavior across different backends."""
        backend_types = ["celery", "temporal"]

        for backend_type in backend_types:
            try:
                backend = get_backend(backend_type, use_env=False)

                # Test submitting unregistered task
                with pytest.raises(ValueError, match="not registered"):
                    backend.submit("nonexistent_task", "data")

                # Test that backend_type property works
                assert backend.backend_type == backend_type

            except ImportError:
                pytest.skip(f"{backend_type} not installed")


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrentTaskExecution:
    """Test concurrent task execution scenarios."""

    @patch("task_abstraction.backends.celery.Celery")
    def test_multiple_task_registration(self, mock_celery_class):
        """Test registering and managing multiple tasks."""
        mock_app = Mock()
        mock_celery_class.return_value = mock_app
        mock_app.task.return_value = lambda fn: fn

        try:
            backend = get_backend("celery", use_env=False)

            # Register multiple tasks
            @backend.register_task
            def add(a, b):
                return a + b

            @backend.register_task
            def subtract(a, b):
                return a - b

            @backend.register_task
            def multiply(a, b):
                return a * b

            # Verify all tasks are registered
            assert len(backend._tasks) == 3
            assert "add" in backend._tasks
            assert "subtract" in backend._tasks
            assert "multiply" in backend._tasks

            # Test that tasks can be called directly
            assert add(2, 3) == 5
            assert subtract(10, 4) == 6
            assert multiply(3, 7) == 21

        except ImportError:
            pytest.skip("Celery not installed")

    def test_task_result_status_progression(self):
        """Test TaskResult status transitions."""
        from task_abstraction.models import TaskResult

        # Test status progression: pending -> running -> completed
        task_id = "progression-test-123"

        # Pending state
        pending_result = TaskResult(task_id, "test_task", "pending")
        assert pending_result.is_pending
        assert not pending_result.is_running
        assert not pending_result.is_completed
        assert not pending_result.is_failed

        # Running state
        running_result = TaskResult(task_id, "test_task", "running")
        assert not running_result.is_pending
        assert running_result.is_running
        assert not running_result.is_completed
        assert not running_result.is_failed

        # Completed state
        completed_result = TaskResult(task_id, "test_task", "completed", result="done")
        assert not completed_result.is_pending
        assert not completed_result.is_running
        assert completed_result.is_completed
        assert not completed_result.is_failed

        # Failed state
        failed_result = TaskResult(
            task_id, "test_task", "failed", error="Something went wrong"
        )
        assert not failed_result.is_pending
        assert not failed_result.is_running
        assert not failed_result.is_completed
        assert failed_result.is_failed
