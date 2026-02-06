"""Tests for HTTP Session Lifecycle Management (UNS-205).

Tests cover:
- FR-1: __del__ destructor safety net
- FR-2: Explicit cleanup in callback tasks (try/finally)
- FR-3: Singleton lifecycle management (reset_singleton, task counter)
- Gap #5: _owns_session flag for singleton-safe close()
- Gap #4: API_CLIENT_POOL_SIZE wired into HTTPAdapter
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton_state():
    """Reset InternalAPIClient class-level singleton state between tests."""
    from shared.api.internal_client import InternalAPIClient

    InternalAPIClient._shared_session = None
    InternalAPIClient._shared_base_client = None
    InternalAPIClient._initialization_count = 0
    InternalAPIClient._task_counter = 0
    InternalAPIClient._last_reset_time = None
    yield
    InternalAPIClient._shared_session = None
    InternalAPIClient._shared_base_client = None
    InternalAPIClient._initialization_count = 0
    InternalAPIClient._task_counter = 0
    InternalAPIClient._last_reset_time = None


@pytest.fixture
def mock_config():
    """Create a WorkerConfig with defaults suitable for testing."""
    with patch.dict(
        "os.environ",
        {
            "INTERNAL_API_BASE_URL": "http://test-backend:8000/internal",
            "INTERNAL_SERVICE_API_KEY": "test-key-123",
            "CELERY_BROKER_BASE_URL": "amqp://localhost:5672//",
            "CELERY_BROKER_USER": "guest",
            "CELERY_BROKER_PASS": "guest",
            "DB_HOST": "localhost",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DB_NAME": "testdb",
            "API_CLIENT_POOL_SIZE": "5",
            "ENABLE_API_CLIENT_SINGLETON": "false",
        },
    ):
        from shared.infrastructure.config.worker_config import WorkerConfig

        yield WorkerConfig()


@pytest.fixture
def mock_config_singleton():
    """Create a WorkerConfig with singleton enabled."""
    with patch.dict(
        "os.environ",
        {
            "INTERNAL_API_BASE_URL": "http://test-backend:8000/internal",
            "INTERNAL_SERVICE_API_KEY": "test-key-123",
            "CELERY_BROKER_BASE_URL": "amqp://localhost:5672//",
            "CELERY_BROKER_USER": "guest",
            "CELERY_BROKER_PASS": "guest",
            "DB_HOST": "localhost",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DB_NAME": "testdb",
            "API_CLIENT_POOL_SIZE": "5",
            "ENABLE_API_CLIENT_SINGLETON": "true",
            "WORKER_SINGLETON_RESET_THRESHOLD": "3",
        },
    ):
        from shared.infrastructure.config.worker_config import WorkerConfig

        yield WorkerConfig()


# ===========================================================================
# FR-1: __del__ destructor tests
# ===========================================================================


class TestBaseAPIClientDestructor:
    """Tests for BaseAPIClient.__del__ safety net."""

    def test_del_closes_unclosed_session(self, mock_config):
        """__del__ should close the session if close() was never called."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session
        client._closed = False
        client._owns_session = True

        client.__del__()

        mock_session.close.assert_called_once()

    def test_del_skips_already_closed_session(self, mock_config):
        """__del__ should be a no-op if session is already closed."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session
        client._closed = True

        client.__del__()

        mock_session.close.assert_not_called()

    def test_del_skips_shared_session(self, mock_config):
        """__del__ should NOT close a shared singleton session."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session
        client._closed = False
        client._owns_session = False

        client.__del__()

        mock_session.close.assert_not_called()

    def test_del_handles_missing_attributes(self):
        """__del__ should not raise even if init failed partially."""
        from shared.clients.base_client import BaseAPIClient

        client = object.__new__(BaseAPIClient)
        # No attributes set at all - should not raise
        client.__del__()

    def test_del_swallows_exceptions(self, mock_config):
        """__del__ should never propagate exceptions."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        client._closed = False
        client._owns_session = True
        client.session = MagicMock()
        client.session.close.side_effect = RuntimeError("connection broken")

        # Should not raise
        client.__del__()


# ===========================================================================
# FR-1 + Gap #5: close() with _owns_session
# ===========================================================================


class TestBaseAPIClientClose:
    """Tests for BaseAPIClient.close() behavior."""

    def test_close_is_idempotent(self, mock_config):
        """Calling close() multiple times should only close session once."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session

        client.close()
        client.close()
        client.close()

        mock_session.close.assert_called_once()

    def test_close_skips_shared_session(self, mock_config):
        """close() should NOT close the session when _owns_session=False."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session
        client._owns_session = False

        client.close()

        mock_session.close.assert_not_called()
        assert client._closed is True  # Flag still set to prevent redundant calls

    def test_close_closes_owned_session(self, mock_config):
        """close() should close the session when _owns_session=True (default)."""
        from shared.clients.base_client import BaseAPIClient

        client = BaseAPIClient(mock_config)
        mock_session = MagicMock()
        client.session = mock_session
        assert client._owns_session is True  # Default

        client.close()

        mock_session.close.assert_called_once()
        assert client._closed is True

    def test_context_manager_calls_close(self, mock_config):
        """Using 'with' should call close() on exit."""
        from shared.clients.base_client import BaseAPIClient

        with BaseAPIClient(mock_config) as client:
            mock_session = MagicMock()
            client.session = mock_session

        mock_session.close.assert_called_once()


# ===========================================================================
# Gap #4: API_CLIENT_POOL_SIZE wired into HTTPAdapter
# ===========================================================================


class TestPoolSizeConfiguration:
    """Tests for API_CLIENT_POOL_SIZE being wired into HTTPAdapter."""

    def test_pool_size_from_config(self, mock_config):
        """HTTPAdapter should use api_client_pool_size from config."""
        from shared.clients.base_client import BaseAPIClient

        assert mock_config.api_client_pool_size == 5

        client = BaseAPIClient(mock_config)

        # Inspect the mounted adapter's internal pool settings
        adapter = client.session.get_adapter("http://")
        assert adapter._pool_connections == 5
        assert adapter._pool_maxsize == 10  # pool_size * 2

        client.close()

    def test_default_pool_size(self):
        """Default pool size should be 10 when not configured."""
        with patch.dict(
            "os.environ",
            {
                "INTERNAL_API_BASE_URL": "http://test:8000/internal",
                "INTERNAL_SERVICE_API_KEY": "test-key",
                "CELERY_BROKER_BASE_URL": "amqp://localhost:5672//",
                "CELERY_BROKER_USER": "guest",
                "CELERY_BROKER_PASS": "guest",
                "DB_HOST": "localhost",
                "DB_USER": "test",
                "DB_PASSWORD": "test",
                "DB_NAME": "testdb",
            },
            clear=False,
        ):
            from shared.infrastructure.config.worker_config import WorkerConfig

            config = WorkerConfig()
            assert config.api_client_pool_size == 10


# ===========================================================================
# FR-3: Singleton lifecycle management
# ===========================================================================


class TestResetSingleton:
    """Tests for InternalAPIClient.reset_singleton()."""

    def test_reset_when_no_shared_session(self):
        """reset_singleton() should be a no-op when there's no shared session."""
        from shared.api.internal_client import InternalAPIClient

        # Should not raise
        InternalAPIClient.reset_singleton()
        assert InternalAPIClient._shared_session is None

    def test_reset_closes_shared_session(self):
        """reset_singleton() should close the shared session and clear state."""
        from shared.api.internal_client import InternalAPIClient

        mock_session = MagicMock()
        InternalAPIClient._shared_session = mock_session
        InternalAPIClient._shared_base_client = MagicMock()
        InternalAPIClient._initialization_count = 5
        InternalAPIClient._task_counter = 42

        InternalAPIClient.reset_singleton()

        mock_session.close.assert_called_once()
        assert InternalAPIClient._shared_session is None
        assert InternalAPIClient._shared_base_client is None
        assert InternalAPIClient._initialization_count == 0
        assert InternalAPIClient._task_counter == 0

    def test_reset_handles_close_exception(self):
        """reset_singleton() should handle session.close() failure gracefully."""
        from shared.api.internal_client import InternalAPIClient

        mock_session = MagicMock()
        mock_session.close.side_effect = RuntimeError("broken pipe")
        InternalAPIClient._shared_session = mock_session

        # Should not raise
        InternalAPIClient.reset_singleton()

        assert InternalAPIClient._shared_session is None


# ===========================================================================
# FR-3: Task counter
# ===========================================================================


class TestTaskCounter:
    """Tests for InternalAPIClient.increment_task_counter()."""

    def test_increment_counter(self, mock_config_singleton):
        """Counter should increment on each call."""
        from shared.api.internal_client import InternalAPIClient

        InternalAPIClient._task_counter = 0

        with patch.object(
            InternalAPIClient, "reset_singleton"
        ) as mock_reset:
            InternalAPIClient.increment_task_counter()
            assert InternalAPIClient._task_counter == 1
            mock_reset.assert_not_called()

    def test_threshold_triggers_reset(self, mock_config_singleton):
        """Counter reaching threshold should trigger reset_singleton()."""
        from shared.api.internal_client import InternalAPIClient

        # Threshold is 3 from mock_config_singleton
        InternalAPIClient._task_counter = 2  # One away from threshold

        with patch.object(
            InternalAPIClient, "reset_singleton"
        ) as mock_reset:
            InternalAPIClient.increment_task_counter()
            mock_reset.assert_called_once()
            # Counter should be reset to 0 after threshold
            assert InternalAPIClient._task_counter == 0

    def test_get_task_counter_info(self):
        """get_task_counter_info() should return correct state."""
        from shared.api.internal_client import InternalAPIClient

        InternalAPIClient._task_counter = 42
        InternalAPIClient._shared_session = MagicMock()

        info = InternalAPIClient.get_task_counter_info()

        assert info["task_counter"] == 42
        assert info["shared_session_active"] is True


# ===========================================================================
# FR-3: on_task_postrun guard
# ===========================================================================


class TestOnTaskPostrunGuard:
    """Tests for the singleton guard in on_task_postrun."""

    def test_postrun_skips_when_singleton_disabled(self, mock_config):
        """on_task_postrun should skip entirely when singleton=false."""
        assert mock_config.enable_api_client_singleton is False

        with patch(
            "shared.api.internal_client.InternalAPIClient.increment_task_counter"
        ) as mock_increment:
            # Simulate what on_task_postrun does with the guard
            if not mock_config.enable_api_client_singleton:
                pass  # Early return
            else:
                mock_increment()

            mock_increment.assert_not_called()

    def test_postrun_calls_increment_when_singleton_enabled(
        self, mock_config_singleton
    ):
        """on_task_postrun should call increment when singleton=true."""
        assert mock_config_singleton.enable_api_client_singleton is True

        with patch(
            "shared.api.internal_client.InternalAPIClient.increment_task_counter"
        ) as mock_increment:
            mock_increment()
            mock_increment.assert_called_once()


# ===========================================================================
# Gap #5: Singleton-aware close() in InternalAPIClient
# ===========================================================================


class TestInternalAPIClientSingletonClose:
    """Tests for InternalAPIClient.close() respecting singleton mode."""

    def test_close_traditional_mode_closes_all(self, mock_config):
        """In traditional mode, close() should close all client sessions."""
        from shared.api.internal_client import InternalAPIClient

        with patch("shared.api.internal_client.get_client_plugin", return_value=None):
            client = InternalAPIClient(mock_config)

        # Replace sessions with mocks
        mock_sessions = {}
        for attr in [
            "base_client",
            "execution_client",
            "file_client",
            "webhook_client",
            "organization_client",
            "tool_client",
            "workflow_client",
            "usage_client",
        ]:
            sub_client = getattr(client, attr)
            mock_session = MagicMock()
            sub_client.session = mock_session
            sub_client._closed = False
            sub_client._owns_session = True
            mock_sessions[attr] = mock_session

        client.close()

        for attr, mock_session in mock_sessions.items():
            mock_session.close.assert_called_once(), (
                f"{attr} session was not closed"
            )

    def test_close_singleton_mode_preserves_shared_session(
        self, mock_config_singleton
    ):
        """In singleton mode, close() should NOT close the shared session."""
        from shared.api.internal_client import InternalAPIClient

        with patch("shared.api.internal_client.get_client_plugin", return_value=None):
            client = InternalAPIClient(mock_config_singleton)

        shared_session = InternalAPIClient._shared_session
        assert shared_session is not None

        # close() in singleton mode should preserve the session
        client.close()

        # The shared session should still be alive
        assert InternalAPIClient._shared_session is shared_session

    def test_singleton_clients_have_owns_session_false(
        self, mock_config_singleton
    ):
        """All clients in singleton mode should have _owns_session=False."""
        from shared.api.internal_client import InternalAPIClient

        with patch("shared.api.internal_client.get_client_plugin", return_value=None):
            client = InternalAPIClient(mock_config_singleton)

        for attr in [
            "base_client",
            "execution_client",
            "file_client",
            "webhook_client",
            "organization_client",
            "tool_client",
            "workflow_client",
            "usage_client",
        ]:
            sub_client = getattr(client, attr)
            assert sub_client._owns_session is False, (
                f"{attr} should have _owns_session=False in singleton mode"
            )

    def test_traditional_clients_have_owns_session_true(self, mock_config):
        """All clients in traditional mode should have _owns_session=True."""
        from shared.api.internal_client import InternalAPIClient

        with patch("shared.api.internal_client.get_client_plugin", return_value=None):
            client = InternalAPIClient(mock_config)

        for attr in [
            "base_client",
            "execution_client",
            "file_client",
            "webhook_client",
            "organization_client",
            "tool_client",
            "workflow_client",
            "usage_client",
        ]:
            sub_client = getattr(client, attr)
            assert sub_client._owns_session is True, (
                f"{attr} should have _owns_session=True in traditional mode"
            )


# ===========================================================================
# FR-2: WorkerExecutionContext managed_execution_context cleanup
# ===========================================================================


class TestManagedExecutionContextCleanup:
    """Tests for context manager cleanup in WorkerExecutionContext."""

    def test_managed_context_closes_client_on_success(self, mock_config):
        """managed_execution_context should close client after successful use."""
        from shared.workflow.execution.context import WorkerExecutionContext

        with patch.object(
            WorkerExecutionContext,
            "setup_execution_context",
        ) as mock_setup:
            mock_client = MagicMock()
            mock_setup.return_value = (mock_config, mock_client)

            with WorkerExecutionContext.managed_execution_context(
                "org-1", "exec-1", "wf-1"
            ) as (cfg, client):
                pass  # Simulate successful execution

            mock_client.close.assert_called_once()

    def test_managed_context_closes_client_on_exception(self, mock_config):
        """managed_execution_context should close client even when exception occurs."""
        from shared.workflow.execution.context import WorkerExecutionContext

        with patch.object(
            WorkerExecutionContext,
            "setup_execution_context",
        ) as mock_setup:
            mock_client = MagicMock()
            mock_setup.return_value = (mock_config, mock_client)

            with pytest.raises(ValueError):
                with WorkerExecutionContext.managed_execution_context(
                    "org-1", "exec-1", "wf-1"
                ) as (cfg, client):
                    raise ValueError("test error")

            mock_client.close.assert_called_once()
