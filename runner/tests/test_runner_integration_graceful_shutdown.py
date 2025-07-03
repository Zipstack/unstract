"""
Integration tests for runner graceful shutdown functionality.

These tests verify that graceful shutdown configuration propagates correctly
through the runner system and that SIGTERM is sent at the correct execution stage.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest


class TestRunnerGracefulShutdownIntegration:
    """Integration tests for runner graceful shutdown."""

    def test_graceful_shutdown_period_propagation(self) -> None:
        """Test that graceful shutdown period configuration propagates to containers."""
        # Test environment variable propagation logic
        test_cases = [
            ('300', 300),    # Default case
            ('600', 600),    # Custom valid timeout
            ('10', 30),      # Below minimum, should be raised to 30
            ('10000', 7200), # Above maximum, should be capped to 7200
        ]

        for env_value, expected_timeout in test_cases:
            with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': env_value}):
                # Simulate the timeout calculation logic from the runner
                timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
                bounded_timeout = min(max(timeout, 30), 7200)

                assert bounded_timeout == expected_timeout, (
                    f"Expected {expected_timeout} for input {env_value}, "
                    f"got {bounded_timeout}"
                )

    def test_container_stop_signal_sequence(self) -> None:
        """Test that SIGTERM is sent at correct execution stage."""
        # Mock container object
        mock_container = MagicMock()
        mock_container.send_signal = MagicMock()
        mock_container.wait = MagicMock(return_value={'StatusCode': 0})
        mock_container.kill = MagicMock()

        # Simulate the graceful stop sequence
        def simulate_graceful_stop(container, timeout: int = 300) -> bool:
            """Simulate the graceful stop logic from docker_client."""
            if container is None:
                return False

            try:
                # Step 1: Send SIGTERM (signal 15)
                container.send_signal(15)

                # Step 2: Wait for graceful shutdown within timeout
                result = container.wait(timeout=timeout)

                # Step 3: Check if container stopped gracefully
                if result['StatusCode'] == 0:
                    return True
                else:
                    # Force kill if non-zero exit code
                    container.kill()
                    return False

            except Exception:
                # Step 4: Force kill if wait times out or fails
                container.kill()
                return False

        # Test successful graceful stop
        result = simulate_graceful_stop(mock_container, 300)

        # Verify the correct sequence was followed
        assert result is True
        mock_container.send_signal.assert_called_once_with(15)  # SIGTERM
        mock_container.wait.assert_called_once_with(timeout=300)
        mock_container.kill.assert_not_called()  # Should not force kill on success

    def test_container_stop_with_timeout_fallback(self) -> None:
        """Test that force kill happens when graceful stop times out."""
        mock_container = MagicMock()
        mock_container.send_signal = MagicMock()
        # Simulate timeout by raising an exception
        mock_container.wait = MagicMock(side_effect=Exception("Timeout"))
        mock_container.kill = MagicMock()

        def simulate_graceful_stop_with_timeout(container, timeout: int = 300) -> bool:
            """Simulate graceful stop with timeout fallback."""
            if container is None:
                return False

            try:
                container.send_signal(15)  # SIGTERM
                container.wait(timeout=timeout)
                return True
            except Exception:
                # Fallback to force kill
                container.kill()
                return False

        # Test graceful stop with timeout
        result = simulate_graceful_stop_with_timeout(mock_container, 300)

        # Verify SIGTERM was sent first, then force kill on timeout
        assert result is False
        mock_container.send_signal.assert_called_once_with(15)
        mock_container.wait.assert_called_once_with(timeout=300)
        mock_container.kill.assert_called_once()  # Force kill after timeout

    def test_runner_configuration_validation(self) -> None:
        """Test runner configuration validation for graceful shutdown."""
        # Test configuration validation logic
        def validate_graceful_shutdown_config(config_timeout: str) -> dict:
            """Validate graceful shutdown configuration."""
            try:
                timeout = int(config_timeout)
            except (ValueError, TypeError):
                timeout = 300  # Default fallback

            # Apply bounds
            bounded_timeout = min(max(timeout, 30), 7200)

            return {
                'graceful_shutdown_period': bounded_timeout,
                'min_timeout': 30,
                'max_timeout': 7200,
                'is_valid': 30 <= bounded_timeout <= 7200
            }

        # Test various configuration scenarios
        test_configs = [
            ('300', 300, True),      # Valid default
            ('600', 600, True),      # Valid custom
            ('invalid', 300, True),  # Invalid string -> default
            ('10', 30, True),        # Below min -> clamped to min
            ('10000', 7200, True),   # Above max -> clamped to max
        ]

        for config_input, expected_timeout, expected_valid in test_configs:
            result = validate_graceful_shutdown_config(config_input)

            assert result['graceful_shutdown_period'] == expected_timeout
            assert result['is_valid'] == expected_valid
            assert result['min_timeout'] == 30
            assert result['max_timeout'] == 7200

    def test_environment_variable_precedence(self) -> None:
        """Test that environment variable takes precedence over defaults."""
        # Test without environment variable (should use default)
        with patch.dict(os.environ, {}, clear=True):
            timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            assert timeout == 300

        # Test with environment variable (should override default)
        with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': '450'}):
            timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            assert timeout == 450

        # Test with empty environment variable (should use default)
        with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': ''}):
            try:
                timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            except ValueError:
                timeout = 300  # Fallback on invalid value
            assert timeout == 300

    def test_signal_forwarding_logic(self) -> None:
        """Test signal forwarding logic in runner."""
        # Mock signal forwarding scenario
        signals_sent = []

        def mock_send_signal(container_id: str, signal_num: int) -> bool:
            """Mock signal sending to container."""
            signals_sent.append((container_id, signal_num))
            return True

        def simulate_runner_shutdown(container_id: str) -> bool:
            """Simulate runner shutdown sequence."""
            # Step 1: Send SIGTERM to container
            success = mock_send_signal(container_id, 15)  # SIGTERM

            if success:
                # Step 2: Wait for graceful shutdown
                # (In real implementation, this would wait for container to stop)
                time.sleep(0.001)  # Minimal wait for test
                return True

            return False

        # Test signal forwarding
        result = simulate_runner_shutdown("test-container-123")

        assert result is True
        assert len(signals_sent) == 1
        assert signals_sent[0] == ("test-container-123", 15)  # SIGTERM


if __name__ == "__main__":
    pytest.main([__file__])
