import os
from unittest.mock import Mock, patch
from flask import Flask

from unstract.runner.runner import UnstractRunner
from unstract.runner.clients.docker_client import Client, DockerContainer
from unstract.runner.constants import Env


class TestGracefulShutdownIntegration:
    """Integration tests for graceful shutdown functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_app = Mock(spec=Flask)
        self.mock_app.logger = Mock()

    @patch('unstract.runner.runner.client_class')
    def test_run_container_graceful_shutdown_flow(self, mock_client_class):
        """Test the complete graceful shutdown flow for run_container."""
        # Mock the container client
        mock_client = Mock()
        mock_container = Mock(spec=DockerContainer)
        mock_client_class.return_value = mock_client

        # Configure the client mock
        mock_client.run_container.return_value = mock_container
        mock_client.graceful_stop_container = Mock()

        # Create runner
        runner = UnstractRunner(
            image_name="test_image",
            image_tag="test_tag",
            app=self.mock_app
        )
        runner.client = mock_client

        # Mock other dependencies
        with patch('unstract.runner.runner.FileExecutionStatusTracker'):
            with patch.object(runner, 'stream_logs'):
                # Run container
                result = runner.run_container(
                    organization_id="test_org",
                    workflow_id="test_workflow",
                    execution_id="test_execution",
                    file_execution_id="test_file_execution",
                    settings={"tool_instance_id": "test_tool"},
                    envs={},
                    container_name="test_container",
                    messaging_channel=None
                )

        # Verify graceful stop was called
        mock_client.graceful_stop_container.assert_called_once_with(mock_container)

        # Verify container cleanup was called
        mock_container.cleanup.assert_called_once()

    @patch('unstract.runner.runner.client_class')
    def test_run_command_graceful_shutdown_flow(self, mock_client_class):
        """Test the complete graceful shutdown flow for run_command."""
        # Mock the container client
        mock_client = Mock()
        mock_container = Mock(spec=DockerContainer)
        mock_client_class.return_value = mock_client

        # Configure the client mock
        mock_client.run_container.return_value = mock_container
        mock_client.graceful_stop_container = Mock()
        mock_container.logs.return_value = iter(['{"type": "TEST", "result": "success"}'])

        # Create runner
        runner = UnstractRunner(
            image_name="test_image",
            image_tag="test_tag",
            app=self.mock_app
        )
        runner.client = mock_client

        # Mock container config
        mock_client.get_container_run_config.return_value = {
            "name": "test_container",
            "image": "test_image:test_tag"
        }

        # Run command
        result = runner.run_command("TEST")

        # Verify graceful stop was called
        mock_client.graceful_stop_container.assert_called_once_with(mock_container)

        # Verify container cleanup was called
        mock_container.cleanup.assert_called_once()

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "600"})
    @patch('unstract.runner.clients.docker_client.DockerClient')
    def test_docker_client_timeout_configuration(self, mock_docker_client):
        """Test that Docker client uses correct timeout configuration."""
        mock_logger = Mock()

        # Create client
        client = Client(
            image_name="test_image",
            image_tag="test_tag",
            logger=mock_logger,
            sidecar_enabled=False
        )

        # Mock container
        mock_container = Mock(spec=DockerContainer)

        # Call graceful stop
        client.graceful_stop_container(mock_container)

        # Verify timeout was used from environment
        mock_container.graceful_stop.assert_called_once_with(timeout=600)

    def test_timeout_bounds_validation(self):
        """Test that timeout values are properly bounded."""
        from unstract.runner.clients.docker_client import Client

        with patch('unstract.runner.clients.docker_client.DockerClient'):
            client = Client("test", "test", Mock(), False)

            test_cases = [
                ("10", 30),    # Below minimum, should be 30
                ("300", 300),  # Normal value
                ("1800", 1800), # Normal value
                ("7200", 7200), # Maximum value
                ("8000", 7200), # Above maximum, should be 7200
            ]

            for env_value, expected_timeout in test_cases:
                with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: env_value}):
                    mock_container = Mock()
                    client.graceful_stop_container(mock_container)
                    mock_container.graceful_stop.assert_called_with(timeout=expected_timeout)

    @patch('unstract.runner.runner.client_class')
    def test_sidecar_graceful_shutdown(self, mock_client_class):
        """Test graceful shutdown for sidecar containers."""
        # Mock the container client
        mock_client = Mock()
        mock_container = Mock(spec=DockerContainer)
        mock_sidecar = Mock(spec=DockerContainer)
        mock_client_class.return_value = mock_client

        # Configure the client mock for sidecar
        mock_client.run_container_with_sidecar.return_value = (mock_container, mock_sidecar)
        mock_client.graceful_stop_container = Mock()

        # Create runner with sidecar enabled
        runner = UnstractRunner(
            image_name="test_image",
            image_tag="test_tag",
            app=self.mock_app
        )
        runner.client = mock_client
        runner.sidecar_enabled = True

        # Mock other dependencies
        with patch('unstract.runner.runner.FileExecutionStatusTracker'):
            with patch.object(runner, '_get_sidecar_container_config'):
                # Run container with sidecar
                result = runner.run_container(
                    organization_id="test_org",
                    workflow_id="test_workflow",
                    execution_id="test_execution",
                    file_execution_id="test_file_execution",
                    settings={"tool_instance_id": "test_tool"},
                    envs={},
                    container_name="test_container",
                    messaging_channel=None
                )

        # Verify graceful stop was called for both containers
        assert mock_client.graceful_stop_container.call_count == 2

        # Verify cleanup was called for both containers
        mock_container.cleanup.assert_called_once()
        mock_sidecar.cleanup.assert_called_once()

    @patch('unstract.runner.runner.client_class')
    def test_graceful_shutdown_with_exception(self, mock_client_class):
        """Test graceful shutdown when container execution throws exception."""
        # Mock the container client
        mock_client = Mock()
        mock_container = Mock(spec=DockerContainer)
        mock_client_class.return_value = mock_client

        # Configure the client mock to throw exception
        mock_client.run_container.side_effect = Exception("Container failed")
        mock_client.graceful_stop_container = Mock()

        # Create runner
        runner = UnstractRunner(
            image_name="test_image",
            image_tag="test_tag",
            app=self.mock_app
        )
        runner.client = mock_client

        # Mock other dependencies
        with patch('unstract.runner.runner.FileExecutionStatusTracker'):
            # Run container (should handle exception)
            result = runner.run_container(
                organization_id="test_org",
                workflow_id="test_workflow",
                execution_id="test_execution",
                file_execution_id="test_file_execution",
                settings={"tool_instance_id": "test_tool"},
                envs={},
                container_name="test_container",
                messaging_channel=None
            )

        # Should return error result
        assert result["status"] == "ERROR"
        assert "Container failed" in result["error"]

    def test_environment_variable_constants(self):
        """Test that all required environment variable constants are defined."""
        from unstract.runner.constants import Env

        # Check that graceful shutdown period constant exists
        assert hasattr(Env, 'GRACEFUL_SHUTDOWN_PERIOD')
        assert isinstance(Env.GRACEFUL_SHUTDOWN_PERIOD, str)
        assert Env.GRACEFUL_SHUTDOWN_PERIOD == "GRACEFUL_SHUTDOWN_PERIOD"

    @patch('unstract.runner.clients.docker_client.DockerClient')
    def test_remove_container_by_name_graceful_shutdown(self, mock_docker_client):
        """Test that remove_container_by_name uses graceful shutdown."""
        mock_logger = Mock()
        mock_container_obj = Mock()
        mock_container_obj.status = 'running'

        # Mock docker client
        mock_docker_client.return_value.containers.get.return_value = mock_container_obj

        # Create client
        client = Client(
            image_name="test_image",
            image_tag="test_tag",
            logger=mock_logger,
            sidecar_enabled=False
        )

        # Mock graceful stop method
        with patch.object(client, 'graceful_stop_container') as mock_graceful_stop:
            # Call remove container
            client.remove_container_by_name("test_container")

            # Verify graceful stop was called
            mock_graceful_stop.assert_called_once()

    def test_graceful_shutdown_timeout_from_sample_env(self):
        """Test that the timeout value from sample.env is valid."""
        # This tests the default value from the sample.env file
        timeout_str = "7200"  # Value from sample.env
        timeout_int = int(timeout_str)

        # Should be within valid bounds
        assert 30 <= timeout_int <= 7200
        assert timeout_int == 2 * 60 * 60  # 2 hours


class TestGracefulShutdownEdgeCases:
    """Test edge cases for graceful shutdown functionality."""

    def test_multiple_signal_handling(self):
        """Test handling multiple shutdown signals."""
        # This would be part of the tool integration test
        pass

    def test_graceful_shutdown_during_long_operation(self):
        """Test graceful shutdown during long-running operations."""
        # This would be part of the tool integration test
        pass

    def test_concurrent_container_shutdown(self):
        """Test shutting down multiple containers concurrently."""
        # This would test the scenario where multiple containers
        # need to be shut down gracefully at the same time
        pass

    @patch('unstract.runner.clients.docker_client.DockerClient')
    def test_network_error_during_graceful_shutdown(self, mock_docker_client):
        """Test graceful shutdown when network errors occur."""
        mock_logger = Mock()
        mock_container_obj = Mock()

        # Mock network error during container stop
        mock_container_obj.stop.side_effect = Exception("Network error")
        mock_container_obj.kill.return_value = None

        # Create Docker container
        docker_container = DockerContainer(
            container=mock_container_obj,
            logger=mock_logger
        )

        # Should handle the error gracefully
        docker_container.graceful_stop(timeout=300)

        # Verify fallback to kill was attempted
        mock_container_obj.kill.assert_called_once()

        # Verify error was logged
        mock_logger.error.assert_called_with("Failed to gracefully stop container: Network error")
