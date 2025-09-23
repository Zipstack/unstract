"""Unit tests for backend factory."""

import pytest
from unittest.mock import patch, Mock

from task_abstraction.factory import (
    register_backend,
    get_available_backends,
    create_backend,
    get_backend,
    BACKEND_REGISTRY
)
from task_abstraction.models import BackendConfig


class MockBackend:
    """Mock backend for testing."""

    def __init__(self, config=None):
        self.config = config
        self.backend_type = "mock"


class TestBackendRegistry:
    """Test backend registration system."""

    def test_register_backend(self):
        """Test registering a backend implementation."""
        # Clear registry first
        original_backends = BACKEND_REGISTRY.copy()
        BACKEND_REGISTRY.clear()

        try:
            register_backend("test", MockBackend)
            assert "test" in BACKEND_REGISTRY
            assert BACKEND_REGISTRY["test"] == MockBackend
        finally:
            # Restore original registry
            BACKEND_REGISTRY.clear()
            BACKEND_REGISTRY.update(original_backends)

    def test_get_available_backends(self):
        """Test getting list of available backends."""
        backends = get_available_backends()
        assert isinstance(backends, list)
        # Should include at least the basic backends
        assert len(backends) > 0

    def test_create_backend_success(self):
        """Test creating a backend successfully."""
        # Register mock backend
        original_backends = BACKEND_REGISTRY.copy()

        try:
            register_backend("mock", MockBackend)

            config = BackendConfig(
                backend_type="mock",
                connection_params={"test": "value"}
            )

            backend = create_backend("mock", config)
            assert isinstance(backend, MockBackend)
            assert backend.config == config
        finally:
            BACKEND_REGISTRY.clear()
            BACKEND_REGISTRY.update(original_backends)

    def test_create_backend_unsupported_type(self):
        """Test creating backend with unsupported type."""
        with pytest.raises(ValueError, match="Backend type 'nonexistent' not supported"):
            create_backend("nonexistent")

    def test_create_backend_import_error(self):
        """Test backend creation when dependencies are missing."""
        # Mock a backend that raises ImportError
        class FailingBackend:
            def __init__(self, config=None):
                raise ImportError("Missing dependency")

        original_backends = BACKEND_REGISTRY.copy()

        try:
            register_backend("failing", FailingBackend)

            with pytest.raises(ImportError, match="Failed to create failing backend"):
                create_backend("failing")
        finally:
            BACKEND_REGISTRY.clear()
            BACKEND_REGISTRY.update(original_backends)


class TestGetBackend:
    """Test the main get_backend function."""

    def setup_method(self):
        """Set up mock backend for each test."""
        self.original_backends = BACKEND_REGISTRY.copy()
        register_backend("mock", MockBackend)

    def teardown_method(self):
        """Restore original backend registry."""
        BACKEND_REGISTRY.clear()
        BACKEND_REGISTRY.update(self.original_backends)

    def test_get_backend_with_config_object(self):
        """Test get_backend with BackendConfig object."""
        config = BackendConfig(
            backend_type="mock",
            connection_params={"test": "value"}
        )

        backend = get_backend(config=config)
        assert isinstance(backend, MockBackend)
        assert backend.config == config

    def test_get_backend_with_backend_type_and_config(self):
        """Test get_backend with both backend_type and config."""
        config = BackendConfig(
            backend_type="mock",
            connection_params={"test": "value"}
        )

        backend = get_backend(backend_type="mock", config=config)
        assert isinstance(backend, MockBackend)

    def test_get_backend_type_mismatch(self):
        """Test get_backend with mismatched backend_type and config."""
        config = BackendConfig(
            backend_type="mock",
            connection_params={"test": "value"}
        )

        with pytest.raises(ValueError, match="Backend type mismatch"):
            get_backend(backend_type="other", config=config)

    @patch('task_abstraction.factory.load_config_from_env')
    def test_get_backend_from_env(self, mock_load_env):
        """Test get_backend loading from environment."""
        mock_config = BackendConfig(
            backend_type="mock",
            connection_params={"from": "env"}
        )
        mock_load_env.return_value = mock_config

        backend = get_backend(backend_type="mock", use_env=True)

        mock_load_env.assert_called_once_with("mock")
        assert isinstance(backend, MockBackend)

    @patch('task_abstraction.factory.get_default_config')
    def test_get_backend_default_config(self, mock_get_default):
        """Test get_backend with default configuration."""
        mock_config = BackendConfig(
            backend_type="mock",
            connection_params={"from": "default"}
        )
        mock_get_default.return_value = mock_config

        backend = get_backend(backend_type="mock", use_env=False)

        mock_get_default.assert_called_once_with("mock")
        assert isinstance(backend, MockBackend)

    @patch('task_abstraction.factory.load_config_from_file')
    def test_get_backend_from_file(self, mock_load_file):
        """Test get_backend loading from file."""
        mock_config = BackendConfig(
            backend_type="mock",
            connection_params={"from": "file"}
        )
        mock_load_file.return_value = mock_config

        backend = get_backend(config="config.yaml")

        mock_load_file.assert_called_once_with("config.yaml")
        assert isinstance(backend, MockBackend)

    def test_get_backend_no_backend_type_no_config(self):
        """Test get_backend without backend_type or config."""
        with pytest.raises(ValueError, match="Backend type must be specified"):
            get_backend()

    @patch('task_abstraction.factory.load_config_from_file')
    def test_get_backend_file_config_type_mismatch(self, mock_load_file):
        """Test get_backend with file config that doesn't match requested type."""
        mock_config = BackendConfig(
            backend_type="mock",
            connection_params={"from": "file"}
        )
        mock_load_file.return_value = mock_config

        with pytest.raises(ValueError, match="Backend type mismatch"):
            get_backend(backend_type="other", config="config.yaml")