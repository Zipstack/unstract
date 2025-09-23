"""Integration tests for Hatchet backend.

These tests require Hatchet SDK to be installed and valid credentials.
Run with: pytest tests/integration/test_hatchet_backend.py -m integration
"""

import pytest
from unittest.mock import patch, Mock

from task_abstraction.backends.hatchet import HatchetBackend
from task_abstraction.models import BackendConfig


@pytest.mark.integration
class TestHatchetBackendIntegration:
    """Integration tests for Hatchet backend."""

    @pytest.fixture
    def hatchet_config(self):
        """Create test Hatchet configuration."""
        return BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "test-token-12345",
                "server_url": "https://app.hatchet.run",
            },
            worker_config={
                "worker_name": "test-worker",
                "max_runs": 50,
            }
        )

    @pytest.fixture
    def hatchet_backend(self, hatchet_config):
        """Create Hatchet backend instance."""
        try:
            backend = HatchetBackend(hatchet_config)
            yield backend
        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    def test_backend_creation(self, hatchet_backend):
        """Test that Hatchet backend can be created."""
        assert hatchet_backend.backend_type == "hatchet"
        assert hatchet_backend.config.backend_type == "hatchet"

    def test_backend_requires_config(self):
        """Test that Hatchet backend requires configuration."""
        with pytest.raises(ValueError, match="Hatchet backend requires configuration"):
            try:
                HatchetBackend()
            except ImportError:
                pytest.skip("Hatchet SDK not installed")

    def test_invalid_config_rejected(self):
        """Test that invalid configuration is rejected."""
        invalid_config = BackendConfig(
            backend_type="hatchet",
            connection_params={"server_url": "https://app.hatchet.run"}  # Missing token
        )

        with pytest.raises(ValueError, match="Invalid Hatchet configuration"):
            try:
                HatchetBackend(invalid_config)
            except ImportError:
                pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_task_registration(self, mock_hatchet_class, hatchet_config):
        """Test registering tasks with Hatchet backend."""
        mock_hatchet = Mock()
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            @backend.register_task
            def process_data(data):
                return {"processed": data}

            assert "process_data" in backend._tasks
            assert "process_data" in backend._workflows

            # Verify Hatchet decorators were used
            assert mock_hatchet.workflow.called
            assert mock_hatchet.step.called

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_task_registration_with_name(self, mock_hatchet_class, hatchet_config):
        """Test registering task with custom name."""
        mock_hatchet = Mock()
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            def transform_data(data):
                return data.upper()

            backend.register_task(transform_data, name="custom_transform")

            assert "custom_transform" in backend._tasks
            assert "custom_transform" in backend._workflows

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_task_submission(self, mock_hatchet_class, hatchet_config):
        """Test submitting tasks for execution."""
        mock_hatchet = Mock()
        mock_workflow_run = Mock()
        mock_workflow_run.workflow_run_id = "test-run-12345"
        mock_hatchet.admin.trigger_workflow.return_value = mock_workflow_run
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            @backend.register_task
            def analyze_text(text):
                return {"length": len(text)}

            task_id = backend.submit("analyze_text", "hello world")

            assert task_id == "test-run-12345"

            # Verify workflow was triggered with correct parameters
            mock_hatchet.admin.trigger_workflow.assert_called_once_with(
                workflow_name="analyze_text_workflow",
                input_data={"args": ["hello world"], "kwargs": {}}
            )

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_task_result_retrieval(self, mock_hatchet_class, hatchet_config):
        """Test retrieving task results."""
        mock_hatchet = Mock()
        mock_workflow_run = Mock()
        mock_workflow_run.status = "SUCCEEDED"
        mock_workflow_run.workflow_version.workflow.name = "test_task_workflow"

        # Mock step with result
        mock_step = Mock()
        mock_step.step_name = "test_task"
        mock_step.output = {"result": "success"}
        mock_workflow_run.steps = [mock_step]

        mock_hatchet.admin.get_workflow_run.return_value = mock_workflow_run
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            result = backend.get_result("test-run-12345")

            assert result.task_id == "test-run-12345"
            assert result.task_name == "test_task"
            assert result.status == "completed"
            assert result.result == {"result": "success"}

            mock_hatchet.admin.get_workflow_run.assert_called_once_with("test-run-12345")

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_task_result_failed(self, mock_hatchet_class, hatchet_config):
        """Test retrieving result for failed task."""
        mock_hatchet = Mock()
        mock_workflow_run = Mock()
        mock_workflow_run.status = "FAILED"
        mock_workflow_run.workflow_version.workflow.name = "failed_task_workflow"
        mock_workflow_run.error = "Task execution failed"

        mock_hatchet.admin.get_workflow_run.return_value = mock_workflow_run
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            result = backend.get_result("failed-run-12345")

            assert result.task_id == "failed-run-12345"
            assert result.status == "failed"
            assert "Task execution failed" in result.error

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_submit_unregistered_task(self, mock_hatchet_class, hatchet_config):
        """Test submitting an unregistered task raises error."""
        mock_hatchet = Mock()
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            with pytest.raises(ValueError, match="Task 'nonexistent' not registered"):
                backend.submit("nonexistent", "data")

        except ImportError:
            pytest.skip("Hatchet SDK not installed")

    @patch('hatchet_sdk.Hatchet')
    def test_connection_check(self, mock_hatchet_class, hatchet_config):
        """Test backend connection checking."""
        mock_hatchet = Mock()
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(hatchet_config)

            # Mock successful connection
            mock_hatchet.admin.get_tenant.return_value = {"id": "test-tenant"}
            assert backend.is_connected()

            # Mock connection failure
            mock_hatchet.admin.get_tenant.side_effect = Exception("Connection failed")
            assert not backend.is_connected()

        except ImportError:
            pytest.skip("Hatchet SDK not installed")


@pytest.mark.integration
@pytest.mark.slow
class TestHatchetWorkerIntegration:
    """Integration tests that require Hatchet worker process."""

    @patch('hatchet_sdk.Hatchet')
    def test_worker_startup_simulation(self, mock_hatchet_class):
        """Test worker startup configuration (without actually starting)."""
        config = BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "test-token-12345",
                "server_url": "https://app.hatchet.run",
            },
            worker_config={
                "worker_name": "integration-test-worker",
                "max_runs": 100,
            }
        )

        mock_hatchet = Mock()
        mock_hatchet_class.return_value = mock_hatchet

        try:
            backend = HatchetBackend(config)

            # Register a test task
            @backend.register_task
            def worker_test_task():
                return "worker integration test"

            assert "worker_test_task" in backend._tasks

            # Verify Hatchet client was configured correctly
            mock_hatchet_class.assert_called_once_with(
                token="test-token-12345",
                server_url="https://app.hatchet.run"
            )

        except ImportError:
            pytest.skip("Hatchet SDK not installed")