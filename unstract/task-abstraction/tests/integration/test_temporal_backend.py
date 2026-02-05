"""Integration tests for Temporal backend.

These tests require Temporal server to be running and temporalio to be installed.
Run with: pytest tests/integration/test_temporal_backend.py -m integration
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from task_abstraction.backends.temporal import TemporalBackend
from task_abstraction.models import BackendConfig


@pytest.mark.integration
class TestTemporalBackendIntegration:
    """Integration tests for Temporal backend."""

    @pytest.fixture
    def temporal_config(self):
        """Create test Temporal configuration."""
        return BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "test-queue",
            },
            worker_config={
                "max_concurrent_activities": 50,
                "max_concurrent_workflow_tasks": 25,
            },
        )

    @pytest.fixture
    def temporal_backend(self, temporal_config):
        """Create Temporal backend instance."""
        try:
            backend = TemporalBackend(temporal_config)
            yield backend
        except ImportError:
            pytest.skip("Temporal SDK not installed")

    def test_backend_creation(self, temporal_backend):
        """Test that Temporal backend can be created."""
        assert temporal_backend.backend_type == "temporal"
        assert temporal_backend.config.backend_type == "temporal"

    def test_backend_with_default_config(self):
        """Test Temporal backend with default configuration."""
        try:
            backend = TemporalBackend()
            assert backend.config.backend_type == "temporal"
            assert backend.config.connection_params["host"] == "localhost"
            assert backend.config.connection_params["port"] == 7233
        except ImportError:
            pytest.skip("Temporal SDK not installed")

    def test_invalid_config_rejected(self):
        """Test that invalid configuration is rejected."""
        invalid_config = BackendConfig(
            backend_type="temporal",
            connection_params={"host": "localhost"},  # Missing required fields
        )

        with pytest.raises(ValueError, match="Invalid Temporal configuration"):
            try:
                TemporalBackend(invalid_config)
            except ImportError:
                pytest.skip("Temporal SDK not installed")

    @patch("temporalio.activity.defn")
    @patch("temporalio.workflow.defn")
    def test_task_registration(
        self, mock_workflow_defn, mock_activity_defn, temporal_backend
    ):
        """Test registering tasks with Temporal backend."""
        mock_activity_defn.return_value = lambda fn: fn
        mock_workflow_defn.return_value = lambda cls: cls

        @temporal_backend.register_task
        def calculate_sum(numbers):
            return sum(numbers)

        assert "calculate_sum" in temporal_backend._tasks
        assert "calculate_sum" in temporal_backend._activities
        assert "calculate_sum" in temporal_backend._workflows

        # Verify Temporal decorators were used
        mock_activity_defn.assert_called_once_with(name="calculate_sum")
        mock_workflow_defn.assert_called_once()

    @patch("temporalio.activity.defn")
    @patch("temporalio.workflow.defn")
    def test_task_registration_with_name(
        self, mock_workflow_defn, mock_activity_defn, temporal_backend
    ):
        """Test registering task with custom name."""
        mock_activity_defn.return_value = lambda fn: fn
        mock_workflow_defn.return_value = lambda cls: cls

        def process_string(text):
            return text.strip().lower()

        temporal_backend.register_task(process_string, name="custom_process")

        assert "custom_process" in temporal_backend._tasks
        assert "custom_process" in temporal_backend._activities
        assert "custom_process" in temporal_backend._workflows

        mock_activity_defn.assert_called_once_with(name="custom_process")

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.client.Client.start_workflow")
    def test_task_submission(self, mock_start_workflow, mock_connect, temporal_backend):
        """Test submitting tasks for execution."""
        # Mock client connection
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        # Mock workflow handle
        mock_handle = Mock()
        mock_handle.id = "test-workflow-12345"
        mock_start_workflow.return_value = mock_handle

        # Register a task first
        @temporal_backend.register_task
        def count_words(text):
            return len(text.split())

        # Submit task
        task_id = temporal_backend.submit("count_words", "hello world test")

        assert task_id == "test-workflow-12345"

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.client.Client.get_workflow_handle")
    def test_task_result_retrieval_completed(
        self, mock_get_handle, mock_connect, temporal_backend
    ):
        """Test retrieving result for completed task."""
        # Mock client
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        # Mock workflow handle and description
        mock_handle = AsyncMock()
        mock_description = Mock()
        mock_description.status = "COMPLETED"  # Use the proper enum value
        mock_handle.describe.return_value = mock_description
        mock_handle.result.return_value = 42

        mock_get_handle.return_value = mock_handle

        result = temporal_backend.get_result("test-workflow-12345")

        assert result.task_id == "test-workflow-12345"
        assert result.status == "completed"
        assert result.result == 42

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.client.Client.get_workflow_handle")
    def test_task_result_retrieval_running(
        self, mock_get_handle, mock_connect, temporal_backend
    ):
        """Test retrieving result for running task."""
        # Mock client
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        # Mock workflow handle and description
        mock_handle = AsyncMock()
        mock_description = Mock()
        mock_description.status = "RUNNING"  # Use the proper enum value
        mock_handle.describe.return_value = mock_description

        mock_get_handle.return_value = mock_handle

        result = temporal_backend.get_result("test-workflow-running")

        assert result.task_id == "test-workflow-running"
        assert result.status == "running"
        assert result.result is None

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.client.Client.get_workflow_handle")
    def test_task_result_retrieval_failed(
        self, mock_get_handle, mock_connect, temporal_backend
    ):
        """Test retrieving result for failed task."""
        # Mock client
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        # Mock workflow handle that raises exception
        mock_handle = AsyncMock()
        mock_description = Mock()
        mock_description.status = "FAILED"
        mock_handle.describe.return_value = mock_description
        mock_handle.result.side_effect = Exception("Workflow failed")

        mock_get_handle.return_value = mock_handle

        result = temporal_backend.get_result("test-workflow-failed")

        assert result.task_id == "test-workflow-failed"
        assert result.status == "failed"
        assert "Workflow failed" in result.error

    def test_submit_unregistered_task(self, temporal_backend):
        """Test submitting an unregistered task raises error."""
        with pytest.raises(ValueError, match="Task 'nonexistent' not registered"):
            temporal_backend.submit("nonexistent", "data")

    @patch("temporalio.client.Client.connect")
    def test_connection_check_success(self, mock_connect, temporal_backend):
        """Test successful connection check."""
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        assert temporal_backend.is_connected()

    @patch("temporalio.client.Client.connect")
    def test_connection_check_failure(self, mock_connect, temporal_backend):
        """Test failed connection check."""
        mock_connect.side_effect = Exception("Connection failed")

        assert not temporal_backend.is_connected()


@pytest.mark.integration
@pytest.mark.slow
class TestTemporalWorkerIntegration:
    """Integration tests that require Temporal worker process."""

    @patch("temporalio.client.Client.connect")
    @patch("temporalio.worker.Worker")
    def test_worker_startup_simulation(self, mock_worker_class, mock_connect):
        """Test worker startup configuration (without actually starting)."""
        config = BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "integration-test-queue",
            },
            worker_config={
                "max_concurrent_activities": 100,
                "max_concurrent_workflow_tasks": 50,
            },
        )

        # Mock client and worker
        mock_client = AsyncMock()
        mock_connect.return_value = mock_client

        mock_worker = AsyncMock()
        mock_worker_class.return_value = mock_worker

        try:
            backend = TemporalBackend(config)

            # Register a test task
            @backend.register_task
            def worker_integration_test():
                return "temporal worker test"

            assert "worker_integration_test" in backend._tasks

            # Note: We can't easily test run_worker without actually running it
            # since it's an async method that blocks

        except ImportError:
            pytest.skip("Temporal SDK not installed")

    @pytest.mark.asyncio
    async def test_async_operations(self):
        """Test async methods work correctly."""
        config = BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "async-test-queue",
            },
        )

        try:
            backend = TemporalBackend(config)

            # Test that we can call async methods
            with patch("temporalio.client.Client.connect") as mock_connect:
                mock_client = AsyncMock()
                mock_connect.return_value = mock_client

                client = await backend._ensure_client()
                assert client == mock_client

        except ImportError:
            pytest.skip("Temporal SDK not installed")
