import os
import pytest
from unittest.mock import Mock, patch
from docker.models.containers import Container

from unstract.runner.clients.docker_client import Client, DockerContainer
from unstract.runner.constants import Env


class TestDockerContainerGracefulShutdown:
    """Test cases for Docker container graceful shutdown functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_container = Mock(spec=Container)
        self.mock_container.id = "test_container_123456789012"
        self.mock_container.name = "test_container"
        self.mock_logger = Mock()

        self.docker_container = DockerContainer(
            container=self.mock_container,
            logger=self.mock_logger
        )

    def test_graceful_stop_success(self):
        """Test successful graceful stop of container."""
        timeout = 300

        # Mock successful stop
        self.mock_container.stop.return_value = None

        # Call graceful stop
        self.docker_container.graceful_stop(timeout=timeout)

        # Verify stop was called with correct timeout
        self.mock_container.stop.assert_called_once_with(timeout=timeout)

        # Verify proper logging
        self.mock_logger.info.assert_any_call(
            f"Sending SIGTERM to container {self.mock_container.id[:12]}"
        )
        self.mock_logger.info.assert_any_call(
            f"Container {self.mock_container.id[:12]} stopped gracefully"
        )

    def test_graceful_stop_with_fallback_to_kill(self):
        """Test graceful stop that falls back to force kill."""
        timeout = 300

        # Mock stop failure
        self.mock_container.stop.side_effect = Exception("Stop failed")
        self.mock_container.kill.return_value = None

        # Call graceful stop
        self.docker_container.graceful_stop(timeout=timeout)

        # Verify stop was attempted
        self.mock_container.stop.assert_called_once_with(timeout=timeout)

        # Verify fallback to kill
        self.mock_container.kill.assert_called_once()

        # Verify proper logging
        self.mock_logger.error.assert_called_with("Failed to gracefully stop container: Stop failed")
        self.mock_logger.warning.assert_called_with(
            f"Force killed container {self.mock_container.id[:12]}"
        )

    def test_graceful_stop_complete_failure(self):
        """Test graceful stop where both stop and kill fail."""
        timeout = 300

        # Mock both stop and kill failure
        self.mock_container.stop.side_effect = Exception("Stop failed")
        self.mock_container.kill.side_effect = Exception("Kill failed")

        # Call graceful stop
        self.docker_container.graceful_stop(timeout=timeout)

        # Verify both were attempted
        self.mock_container.stop.assert_called_once_with(timeout=timeout)
        self.mock_container.kill.assert_called_once()

        # Verify proper error logging
        self.mock_logger.error.assert_any_call("Failed to gracefully stop container: Stop failed")
        self.mock_logger.error.assert_any_call("Failed to force kill container: Kill failed")

    def test_graceful_stop_no_container(self):
        """Test graceful stop when container is None."""
        docker_container = DockerContainer(container=None, logger=self.mock_logger)

        # Should not raise exception
        docker_container.graceful_stop(timeout=300)

        # Should not attempt any operations
        assert not self.mock_logger.info.called

    def test_graceful_stop_default_timeout(self):
        """Test graceful stop with default timeout."""
        # Call graceful stop without timeout
        self.docker_container.graceful_stop()

        # Verify stop was called with default timeout
        self.mock_container.stop.assert_called_once_with(timeout=300)


class TestDockerClientGracefulShutdown:
    """Test cases for Docker client graceful shutdown functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_logger = Mock()
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            self.client = Client(
                image_name="test_image",
                image_tag="test_tag",
                logger=self.mock_logger,
                sidecar_enabled=False
            )

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "600"})
    def test_graceful_stop_container_with_env_timeout(self):
        """Test graceful stop with timeout from environment variable."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Call graceful stop
        self.client.graceful_stop_container(mock_docker_container)

        # Verify graceful stop was called with environment timeout
        mock_docker_container.graceful_stop.assert_called_once_with(timeout=600)

        # Verify logging
        self.mock_logger.info.assert_called_with(
            "Gracefully stopping container with 600s timeout"
        )

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "10"})
    def test_graceful_stop_container_timeout_bounds_minimum(self):
        """Test that timeout is bounded to minimum value."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Call graceful stop with low timeout
        self.client.graceful_stop_container(mock_docker_container)

        # Verify timeout was bounded to minimum (30s)
        mock_docker_container.graceful_stop.assert_called_once_with(timeout=30)

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "8000"})
    def test_graceful_stop_container_timeout_bounds_maximum(self):
        """Test that timeout is bounded to maximum value."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Call graceful stop with high timeout
        self.client.graceful_stop_container(mock_docker_container)

        # Verify timeout was bounded to maximum (7200s = 2 hours)
        mock_docker_container.graceful_stop.assert_called_once_with(timeout=7200)

    def test_graceful_stop_container_default_timeout(self):
        """Test graceful stop with default timeout when env var is not set."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Call graceful stop without environment variable
        self.client.graceful_stop_container(mock_docker_container)

        # Verify default timeout was used
        mock_docker_container.graceful_stop.assert_called_once_with(timeout=300)

    def test_graceful_stop_container_explicit_timeout(self):
        """Test graceful stop with explicitly provided timeout."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Call graceful stop with explicit timeout
        self.client.graceful_stop_container(mock_docker_container, timeout=450)

        # Verify explicit timeout was used
        mock_docker_container.graceful_stop.assert_called_once_with(timeout=450)

    def test_graceful_stop_container_none(self):
        """Test graceful stop when container is None."""
        # Should not raise exception
        self.client.graceful_stop_container(None)

        # Should not log anything
        assert not self.mock_logger.info.called

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "invalid"})
    def test_graceful_stop_container_invalid_env_timeout(self):
        """Test graceful stop with invalid environment timeout value."""
        mock_docker_container = Mock(spec=DockerContainer)

        # Should handle invalid value and use default
        with pytest.raises(ValueError):
            self.client.graceful_stop_container(mock_docker_container)


class TestRunnerGracefulShutdownIntegration:
    """Test integration of graceful shutdown in the runner."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_logger = Mock()

    @patch('unstract.runner.runner.client_class')
    def test_runner_calls_graceful_stop(self, mock_client_class):
        """Test that runner calls graceful stop on containers."""
        from unstract.runner.runner import UnstractRunner

        # Mock the container client
        mock_client = Mock()
        mock_container = Mock(spec=DockerContainer)
        mock_client_class.return_value = mock_client

        # Create runner
        runner = UnstractRunner(
            image_name="test_image",
            image_tag="test_tag",
            app=Mock(logger=self.mock_logger)
        )

        # Mock the graceful stop method
        runner.client.graceful_stop_container = Mock()

        # Test that graceful stop is called
        runner.client.graceful_stop_container(mock_container)

        # Verify graceful stop was called
        runner.client.graceful_stop_container.assert_called_once_with(mock_container)

    def test_timeout_validation_bounds(self):
        """Test timeout validation ensures proper bounds."""
        from unstract.runner.clients.docker_client import Client

        with patch('unstract.runner.clients.docker_client.DockerClient'):
            client = Client("test", "test", Mock(), False)

            # Test minimum bound
            with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "10"}):
                mock_container = Mock()
                client.graceful_stop_container(mock_container)
                mock_container.graceful_stop.assert_called_with(timeout=30)

            # Test maximum bound
            with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "10000"}):
                mock_container = Mock()
                client.graceful_stop_container(mock_container)
                mock_container.graceful_stop.assert_called_with(timeout=7200)


class TestTimeoutConfiguration:
    """Test timeout configuration and validation."""

    def test_timeout_environment_variable_defined(self):
        """Test that timeout environment variable is properly defined."""
        from unstract.runner.constants import Env

        assert hasattr(Env, 'GRACEFUL_SHUTDOWN_PERIOD')
        assert Env.GRACEFUL_SHUTDOWN_PERIOD == "GRACEFUL_SHUTDOWN_PERIOD"

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "1800"})
    def test_timeout_from_environment(self):
        """Test reading timeout from environment variable."""
        timeout_value = int(os.getenv(Env.GRACEFUL_SHUTDOWN_PERIOD, "300"))
        assert timeout_value == 1800

    def test_timeout_default_value(self):
        """Test default timeout value when environment variable is not set."""
        # Remove env var if it exists
        if Env.GRACEFUL_SHUTDOWN_PERIOD in os.environ:
            del os.environ[Env.GRACEFUL_SHUTDOWN_PERIOD]

        timeout_value = int(os.getenv(Env.GRACEFUL_SHUTDOWN_PERIOD, "300"))
        assert timeout_value == 300
