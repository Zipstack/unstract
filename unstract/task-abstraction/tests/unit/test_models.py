"""Unit tests for task abstraction models."""

import pytest
from datetime import datetime

from task_abstraction.models import TaskResult, BackendConfig


class TestTaskResult:
    """Test TaskResult model functionality."""

    def test_task_result_creation(self):
        """Test basic TaskResult creation."""
        result = TaskResult(
            task_id="test-123",
            task_name="test_task",
            status="completed",
            result={"success": True}
        )

        assert result.task_id == "test-123"
        assert result.task_name == "test_task"
        assert result.status == "completed"
        assert result.result == {"success": True}
        assert result.error is None

    def test_task_result_status_properties(self):
        """Test TaskResult status property methods."""
        # Test pending
        pending = TaskResult("1", "task", "pending")
        assert pending.is_pending
        assert not pending.is_running
        assert not pending.is_completed
        assert not pending.is_failed

        # Test running
        running = TaskResult("2", "task", "running")
        assert not running.is_pending
        assert running.is_running
        assert not running.is_completed
        assert not running.is_failed

        # Test completed
        completed = TaskResult("3", "task", "completed", result="done")
        assert not completed.is_pending
        assert not completed.is_running
        assert completed.is_completed
        assert not completed.is_failed

        # Test failed
        failed = TaskResult("4", "task", "failed", error="Something went wrong")
        assert not failed.is_pending
        assert not failed.is_running
        assert not failed.is_completed
        assert failed.is_failed

    def test_task_result_duration(self):
        """Test TaskResult duration calculation."""
        start_time = datetime(2023, 1, 1, 12, 0, 0)
        end_time = datetime(2023, 1, 1, 12, 0, 5)  # 5 seconds later

        result = TaskResult(
            task_id="test",
            task_name="test",
            status="completed",
            started_at=start_time,
            completed_at=end_time
        )

        assert result.duration == 5.0

    def test_task_result_duration_no_times(self):
        """Test duration when times are not set."""
        result = TaskResult("test", "test", "pending")
        assert result.duration is None

    def test_task_result_duration_only_start(self):
        """Test duration when only start time is set."""
        result = TaskResult(
            "test", "test", "running",
            started_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        assert result.duration is None


class TestBackendConfig:
    """Test BackendConfig model functionality."""

    def test_backend_config_creation(self):
        """Test basic BackendConfig creation."""
        config = BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0"
            }
        )

        assert config.backend_type == "celery"
        assert config.connection_params["broker_url"] == "redis://localhost:6379/0"
        assert config.worker_config == {}

    def test_backend_config_with_worker_config(self):
        """Test BackendConfig with worker configuration."""
        config = BackendConfig(
            backend_type="celery",
            connection_params={"broker_url": "redis://localhost:6379/0"},
            worker_config={"concurrency": 8, "max_tasks_per_child": 200}
        )

        assert config.worker_config["concurrency"] == 8
        assert config.worker_config["max_tasks_per_child"] == 200

    def test_celery_config_validation(self):
        """Test Celery configuration validation."""
        # Valid config
        valid_config = BackendConfig(
            backend_type="celery",
            connection_params={"broker_url": "redis://localhost:6379/0"}
        )
        assert valid_config.validate()

        # Invalid config - missing broker_url
        invalid_config = BackendConfig(
            backend_type="celery",
            connection_params={"result_backend": "redis://localhost:6379/0"}
        )
        assert not invalid_config.validate()

    def test_hatchet_config_validation(self):
        """Test Hatchet configuration validation."""
        # Valid config
        valid_config = BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "test-token",
                "server_url": "https://app.hatchet.run"
            }
        )
        assert valid_config.validate()

        # Invalid config - missing token
        invalid_config = BackendConfig(
            backend_type="hatchet",
            connection_params={"server_url": "https://app.hatchet.run"}
        )
        assert not invalid_config.validate()

    def test_temporal_config_validation(self):
        """Test Temporal configuration validation."""
        # Valid config
        valid_config = BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "test-queue"
            }
        )
        assert valid_config.validate()

        # Invalid config - missing required fields
        invalid_config = BackendConfig(
            backend_type="temporal",
            connection_params={"host": "localhost"}
        )
        assert not invalid_config.validate()

    def test_invalid_backend_type(self):
        """Test validation with invalid backend type."""
        config = BackendConfig(
            backend_type="invalid",
            connection_params={}
        )
        assert not config.validate()

    def test_post_init_worker_config(self):
        """Test that worker_config is initialized if None."""
        config = BackendConfig(
            backend_type="celery",
            connection_params={"broker_url": "redis://localhost:6379/0"},
            worker_config=None
        )
        assert config.worker_config == {}