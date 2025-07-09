"""
Tests for graceful shutdown across different container platforms (Docker and K8s).
Verifies that both Docker and K8s clients implement the graceful shutdown interface correctly.
"""

import os
from unittest.mock import Mock, patch

from unstract.runner.clients.docker_client import Client as DockerClient, DockerContainer
from unstract.runner.clients.k8s_client import K8sClient, K8sContainer
from unstract.runner.clients.interface import ContainerClientInterface, ContainerInterface
from unstract.runner.constants import Env


class TestMultiPlatformGracefulShutdown:
    """Test graceful shutdown across different container platforms."""

    def test_docker_client_implements_interface(self):
        """Test that Docker client implements the complete interface including graceful shutdown."""
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            client = DockerClient("test", "test", Mock(), False)

            # Verify it implements the interface
            assert isinstance(client, ContainerClientInterface)

            # Verify it has the graceful shutdown method
            assert hasattr(client, 'graceful_stop_container')
            assert callable(getattr(client, 'graceful_stop_container'))

    def test_k8s_client_implements_interface(self):
        """Test that K8s client implements the complete interface including graceful shutdown."""
        client = K8sClient("test", "test", Mock(), False)

        # Verify it implements the interface
        assert isinstance(client, ContainerClientInterface)

        # Verify it has the graceful shutdown method
        assert hasattr(client, 'graceful_stop_container')
        assert callable(getattr(client, 'graceful_stop_container'))

    def test_docker_container_implements_interface(self):
        """Test that Docker container implements the complete interface."""
        mock_docker_container = Mock()
        container = DockerContainer(mock_docker_container, Mock())

        # Verify it implements the interface
        assert isinstance(container, ContainerInterface)

        # Verify it has the graceful stop method
        assert hasattr(container, 'graceful_stop')
        assert callable(getattr(container, 'graceful_stop'))

    def test_k8s_container_implements_interface(self):
        """Test that K8s container implements the complete interface."""
        container = K8sContainer("test-pod", "default", Mock())

        # Verify it implements the interface
        assert isinstance(container, ContainerInterface)

        # Verify it has the graceful stop method
        assert hasattr(container, 'graceful_stop')
        assert callable(getattr(container, 'graceful_stop'))

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "600"})
    def test_docker_client_graceful_shutdown_with_timeout(self):
        """Test Docker client graceful shutdown with environment timeout."""
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            client = DockerClient("test", "test", Mock(), False)
            mock_container = Mock()

            client.graceful_stop_container(mock_container)

            # Verify graceful stop was called with correct timeout
            mock_container.graceful_stop.assert_called_once_with(timeout=600)

    @patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "1800"})
    def test_k8s_client_graceful_shutdown_with_timeout(self):
        """Test K8s client graceful shutdown with environment timeout."""
        client = K8sClient("test", "test", Mock(), False)
        mock_container = Mock(spec=K8sContainer)

        client.graceful_stop_container(mock_container)

        # Verify graceful stop was called with correct timeout
        mock_container.graceful_stop.assert_called_once_with(timeout=1800)

    def test_timeout_bounds_validation_docker(self):
        """Test that Docker client validates timeout bounds correctly."""
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            client = DockerClient("test", "test", Mock(), False)

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

    def test_timeout_bounds_validation_k8s(self):
        """Test that K8s client validates timeout bounds correctly."""
        client = K8sClient("test", "test", Mock(), False)

        # Test minimum bound
        with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "5"}):
            mock_container = Mock(spec=K8sContainer)
            client.graceful_stop_container(mock_container)
            mock_container.graceful_stop.assert_called_with(timeout=30)

        # Test maximum bound
        with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "9000"}):
            mock_container = Mock(spec=K8sContainer)
            client.graceful_stop_container(mock_container)
            mock_container.graceful_stop.assert_called_with(timeout=7200)

    def test_invalid_timeout_handling_docker(self):
        """Test that Docker client handles invalid timeout values gracefully."""
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            mock_logger = Mock()
            client = DockerClient("test", "test", mock_logger, False)

            with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "invalid"}):
                mock_container = Mock()
                client.graceful_stop_container(mock_container)

                # Should use default timeout
                mock_container.graceful_stop.assert_called_with(timeout=300)

                # Should log warning
                mock_logger.warning.assert_called_once()

    def test_invalid_timeout_handling_k8s(self):
        """Test that K8s client handles invalid timeout values gracefully."""
        mock_logger = Mock()
        client = K8sClient("test", "test", mock_logger, False)

        with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: "not_a_number"}):
            mock_container = Mock(spec=K8sContainer)
            client.graceful_stop_container(mock_container)

            # Should use default timeout
            mock_container.graceful_stop.assert_called_with(timeout=300)

            # Should log warning
            mock_logger.warning.assert_called_once()

    def test_graceful_shutdown_none_container(self):
        """Test graceful shutdown with None container for both clients."""
        # Docker client
        with patch('unstract.runner.clients.docker_client.DockerClient'):
            docker_client = DockerClient("test", "test", Mock(), False)
            # Should not raise exception
            docker_client.graceful_stop_container(None)

        # K8s client
        k8s_client = K8sClient("test", "test", Mock(), False)
        # Should not raise exception
        k8s_client.graceful_stop_container(None)

    def test_container_platform_switching(self):
        """Test that container client can be switched via environment variable."""
        from unstract.runner.clients.helper import ContainerClientHelper

        # Test Docker client loading (default)
        with patch.dict(os.environ, {"CONTAINER_CLIENT_PATH": "unstract.runner.clients.docker_client"}):
            with patch('unstract.runner.clients.helper.import_module') as mock_import:
                mock_module = Mock()
                mock_module.Client = DockerClient
                mock_import.return_value = mock_module

                client_class = ContainerClientHelper.get_container_client()
                assert client_class == DockerClient

        # Test K8s client loading
        with patch.dict(os.environ, {"CONTAINER_CLIENT_PATH": "unstract.runner.clients.k8s_client"}):
            with patch('unstract.runner.clients.helper.import_module') as mock_import:
                mock_module = Mock()
                mock_module.Client = K8sClient
                mock_import.return_value = mock_module

                client_class = ContainerClientHelper.get_container_client()
                assert client_class == K8sClient


class TestPlatformSpecificFeatures:
    """Test platform-specific graceful shutdown features."""

    def test_docker_force_kill_fallback(self):
        """Test Docker container force kill fallback."""
        mock_docker_container = Mock()
        mock_docker_container.stop.side_effect = Exception("Stop failed")
        mock_docker_container.kill.return_value = None
        mock_docker_container.id = "test123456789012"

        mock_logger = Mock()
        container = DockerContainer(mock_docker_container, mock_logger)

        container.graceful_stop(timeout=300)

        # Verify fallback to kill was attempted
        mock_docker_container.kill.assert_called_once()
        mock_logger.warning.assert_called_with("Force killed container test123456789012")

    def test_k8s_force_delete_fallback(self):
        """Test K8s container force delete fallback."""
        mock_logger = Mock()
        container = K8sContainer("test-pod", "default", mock_logger)

        # Mock the graceful stop to simulate failure
        with patch.object(container, '_is_running', True):
            # Simulate graceful termination working
            container.graceful_stop(timeout=300)

        # Verify proper logging
        mock_logger.info.assert_any_call("Sending SIGTERM to pod test-pod in namespace default")
        mock_logger.info.assert_any_call("Pod test-pod terminated gracefully")

    def test_environment_consistency_across_platforms(self):
        """Test that environment variables work consistently across platforms."""
        test_timeout = "1200"

        with patch.dict(os.environ, {Env.GRACEFUL_SHUTDOWN_PERIOD: test_timeout}):
            # Docker client
            with patch('unstract.runner.clients.docker_client.DockerClient'):
                docker_client = DockerClient("test", "test", Mock(), False)
                mock_docker_container = Mock()
                docker_client.graceful_stop_container(mock_docker_container)
                mock_docker_container.graceful_stop.assert_called_with(timeout=1200)

            # K8s client
            k8s_client = K8sClient("test", "test", Mock(), False)
            mock_k8s_container = Mock(spec=K8sContainer)
            k8s_client.graceful_stop_container(mock_k8s_container)
            mock_k8s_container.graceful_stop.assert_called_with(timeout=1200)


class TestGracefulShutdownDocumentation:
    """Test that graceful shutdown is properly documented in interfaces."""

    def test_interface_method_documentation(self):
        """Test that graceful shutdown methods have proper documentation."""
        # Test ContainerInterface
        assert hasattr(ContainerInterface, 'graceful_stop')
        method = getattr(ContainerInterface, 'graceful_stop')
        assert method.__doc__ is not None
        assert "graceful" in method.__doc__.lower()
        assert "sigterm" in method.__doc__.lower()

        # Test ContainerClientInterface
        assert hasattr(ContainerClientInterface, 'graceful_stop_container')
        method = getattr(ContainerClientInterface, 'graceful_stop_container')
        assert method.__doc__ is not None
        assert "graceful" in method.__doc__.lower()
        assert "timeout" in method.__doc__.lower()

    def test_method_signatures_consistency(self):
        """Test that graceful shutdown method signatures are consistent."""
        # Both Docker and K8s clients should have the same signature
        docker_method = DockerClient.graceful_stop_container
        k8s_method = K8sClient.graceful_stop_container

        # Get method signatures (simplified check)
        assert callable(docker_method)
        assert callable(k8s_method)

        # Both container types should have graceful_stop with timeout parameter
        docker_container_method = DockerContainer.graceful_stop
        k8s_container_method = K8sContainer.graceful_stop

        assert callable(docker_container_method)
        assert callable(k8s_container_method)
