"""Unit tests for configuration management."""

import os
import tempfile
from unittest.mock import patch

import pytest
from task_abstraction.config import (
    get_default_config,
    load_config_from_env,
    load_config_from_file,
)


class TestLoadConfigFromEnv:
    """Test environment-based configuration loading."""

    @patch.dict(
        os.environ,
        {
            "CELERY_BROKER_URL": "redis://test:6379/1",
            "CELERY_RESULT_BACKEND": "redis://test:6379/2",
            "CELERY_WORKER_CONCURRENCY": "8",
        },
    )
    def test_load_celery_config_from_env(self):
        """Test loading Celery config from environment."""
        config = load_config_from_env("celery")

        assert config.backend_type == "celery"
        assert config.connection_params["broker_url"] == "redis://test:6379/1"
        assert config.connection_params["result_backend"] == "redis://test:6379/2"
        assert config.worker_config["concurrency"] == 8

    @patch.dict(
        os.environ,
        {
            "HATCHET_TOKEN": "test-token-123",
            "HATCHET_SERVER_URL": "https://test.hatchet.run",
            "HATCHET_WORKER_NAME": "test-worker",
        },
    )
    def test_load_hatchet_config_from_env(self):
        """Test loading Hatchet config from environment."""
        config = load_config_from_env("hatchet")

        assert config.backend_type == "hatchet"
        assert config.connection_params["token"] == "test-token-123"
        assert config.connection_params["server_url"] == "https://test.hatchet.run"
        assert config.worker_config["worker_name"] == "test-worker"

    @patch.dict(
        os.environ,
        {
            "TEMPORAL_HOST": "test.temporal.io",
            "TEMPORAL_PORT": "7234",
            "TEMPORAL_NAMESPACE": "test-namespace",
            "TEMPORAL_TASK_QUEUE": "test-queue",
        },
    )
    def test_load_temporal_config_from_env(self):
        """Test loading Temporal config from environment."""
        config = load_config_from_env("temporal")

        assert config.backend_type == "temporal"
        assert config.connection_params["host"] == "test.temporal.io"
        assert config.connection_params["port"] == 7234
        assert config.connection_params["namespace"] == "test-namespace"
        assert config.connection_params["task_queue"] == "test-queue"

    def test_load_config_from_env_defaults(self):
        """Test loading config with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = load_config_from_env("celery")

            assert config.connection_params["broker_url"] == "redis://localhost:6379/0"
            assert config.worker_config["concurrency"] == 4

    def test_load_config_from_env_invalid_backend(self):
        """Test loading config for invalid backend type."""
        with pytest.raises(ValueError, match="Unsupported backend type: invalid"):
            load_config_from_env("invalid")

    def test_load_config_validates(self):
        """Test that loaded config is validated."""
        with patch.dict(os.environ, {}, clear=True):
            config = load_config_from_env("celery")
            assert config.validate()


class TestGetDefaultConfig:
    """Test default configuration generation."""

    def test_get_default_celery_config(self):
        """Test default Celery configuration."""
        config = get_default_config("celery")

        assert config.backend_type == "celery"
        assert config.connection_params["broker_url"] == "redis://localhost:6379/0"
        assert config.connection_params["result_backend"] == "redis://localhost:6379/0"
        assert config.worker_config["concurrency"] == 4
        assert config.validate()

    def test_get_default_hatchet_config(self):
        """Test default Hatchet configuration."""
        config = get_default_config("hatchet")

        assert config.backend_type == "hatchet"
        assert config.connection_params["token"] == "your-hatchet-token"
        assert config.connection_params["server_url"] == "https://app.hatchet.run"
        assert config.worker_config["worker_name"] == "default-worker"
        # Note: This won't validate because token is placeholder

    def test_get_default_temporal_config(self):
        """Test default Temporal configuration."""
        config = get_default_config("temporal")

        assert config.backend_type == "temporal"
        assert config.connection_params["host"] == "localhost"
        assert config.connection_params["port"] == 7233
        assert config.connection_params["namespace"] == "default"
        assert config.connection_params["task_queue"] == "default-queue"
        assert config.validate()

    def test_get_default_config_invalid_backend(self):
        """Test default config for invalid backend type."""
        with pytest.raises(ValueError, match="Unsupported backend type: invalid"):
            get_default_config("invalid")


class TestLoadConfigFromFile:
    """Test file-based configuration loading."""

    def test_load_config_from_yaml_file(self):
        """Test loading config from YAML file."""
        yaml_content = """
backend: celery
celery:
  broker_url: redis://file:6379/0
  result_backend: redis://file:6379/1
worker:
  concurrency: 16
  max_tasks_per_child: 200
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = load_config_from_file(f.name)

                assert config.backend_type == "celery"
                assert config.connection_params["broker_url"] == "redis://file:6379/0"
                assert config.connection_params["result_backend"] == "redis://file:6379/1"
                assert config.worker_config["concurrency"] == 16
                assert config.worker_config["max_tasks_per_child"] == 200
                assert config.validate()

            finally:
                os.unlink(f.name)

    def test_load_config_missing_file(self):
        """Test loading config from non-existent file."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config_from_file("/nonexistent/config.yaml")

    def test_load_config_missing_backend_type(self):
        """Test loading config without backend type specified."""
        yaml_content = """
celery:
  broker_url: redis://localhost:6379/0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                with pytest.raises(ValueError, match="Backend type must be specified"):
                    load_config_from_file(f.name)
            finally:
                os.unlink(f.name)

    def test_load_config_invalid_config(self):
        """Test loading invalid configuration."""
        yaml_content = """
backend: celery
celery:
  # Missing required broker_url
  result_backend: redis://localhost:6379/0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                with pytest.raises(
                    ValueError, match="Invalid configuration for backend type"
                ):
                    load_config_from_file(f.name)
            finally:
                os.unlink(f.name)

    @patch("task_abstraction.config.YAML_AVAILABLE", False)
    def test_load_config_yaml_not_available(self):
        """Test loading config when PyYAML is not available."""
        with pytest.raises(ImportError, match="PyYAML is not installed"):
            load_config_from_file("config.yaml")
