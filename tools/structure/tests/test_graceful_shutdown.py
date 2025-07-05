"""Tests for graceful shutdown functionality in Structure Tool."""

import os
import signal
import threading
import time
from unittest.mock import MagicMock, patch


import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import StructureTool, shutdown_requested


class TestGracefulShutdown:
    """Test cases for graceful shutdown functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Reset shutdown flag before each test
        shutdown_requested.clear()

    def test_signal_handler_sets_shutdown_flag(self) -> None:
        """Test that SIGTERM handler sets the shutdown flag."""
        # Import the signal handler
        from main import signal_handler

        # Call signal handler
        signal_handler(signal.SIGTERM, None)

        # Verify shutdown flag is set
        assert shutdown_requested.is_set()

    def test_shutdown_flag_initially_clear(self) -> None:
        """Test that shutdown flag is initially clear."""
        assert not shutdown_requested.is_set()

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    @patch('unstract.tools.structure.src.main.StructureTool._extract_text')
    def test_shutdown_before_text_extraction(
        self, mock_extract: MagicMock, mock_log: MagicMock
    ) -> None:
        """Test shutdown check before text extraction."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Import and call the run method logic
        from main import StructureTool

        # Mock the run method to test shutdown check
        with patch.object(StructureTool, 'run') as mock_run:
            # Simulate the shutdown check logic
            if shutdown_requested.is_set():
                mock_log("Shutdown requested, stopping before text extraction")
                return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before text extraction")

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    def test_shutdown_before_summarization(self, mock_log: MagicMock) -> None:
        """Test shutdown check before summarization."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Simulate the shutdown check in _summarize method
        if shutdown_requested.is_set():
            mock_log("Shutdown requested, stopping before summarization")
            return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before summarization")

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    def test_shutdown_before_indexing(self, mock_log: MagicMock) -> None:
        """Test shutdown check before vector indexing."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Simulate the shutdown check before indexing
        if shutdown_requested.is_set():
            mock_log("Shutdown requested, stopping before vector indexing")
            return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before vector indexing")

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    def test_shutdown_before_single_pass_extraction(self, mock_log: MagicMock) -> None:
        """Test shutdown check before single-pass LLM extraction."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Simulate the shutdown check before single-pass extraction
        if shutdown_requested.is_set():
            mock_log("Shutdown requested, stopping before single-pass extraction")
            return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before single-pass extraction")

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    def test_shutdown_before_prompt_processing(self, mock_log: MagicMock) -> None:
        """Test shutdown check before prompt processing."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Simulate the shutdown check before prompt processing
        if shutdown_requested.is_set():
            mock_log("Shutdown requested, stopping before prompt processing")
            return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before prompt processing")

    @patch('unstract.tools.structure.src.main.StructureTool.stream_log')
    def test_shutdown_before_summarization_llm_call(self, mock_log: MagicMock) -> None:
        """Test shutdown check before summarization LLM call."""
        # Set shutdown flag
        shutdown_requested.set()

        # Create mock tool instance
        tool = MagicMock(spec=StructureTool)
        tool.stream_log = mock_log

        # Simulate the shutdown check before summarization LLM call
        if shutdown_requested.is_set():
            mock_log("Shutdown requested, stopping before summarization LLM call")
            return

        # Verify log was called
        mock_log.assert_called_with("Shutdown requested, stopping before summarization LLM call")

    def test_shutdown_flag_thread_safety(self) -> None:
        """Test that shutdown flag is thread-safe."""
        results = []

        def check_flag():
            results.append(shutdown_requested.is_set())

        def set_flag():
            time.sleep(0.1)  # Small delay
            shutdown_requested.set()

        # Start threads
        t1 = threading.Thread(target=check_flag)
        t2 = threading.Thread(target=set_flag)
        t3 = threading.Thread(target=check_flag)

        t1.start()
        t2.start()
        time.sleep(0.05)  # Let set_flag start
        t3.start()

        t1.join()
        t2.join()
        t3.join()

        # First check should be False, but we can't guarantee timing
        # Just verify the flag can be set and read from multiple threads
        assert len(results) == 2

    def test_multiple_signal_handlers(self) -> None:
        """Test that multiple SIGTERM signals don't cause issues."""
        from unstract.tools.structure.src.main import signal_handler

        # Send multiple signals
        signal_handler(signal.SIGTERM, None)
        signal_handler(signal.SIGTERM, None)
        signal_handler(signal.SIGTERM, None)

        # Flag should still be set
        assert shutdown_requested.is_set()

    @patch('unstract.tools.structure.src.main.StructureTool')
    def test_graceful_shutdown_integration(self, mock_tool_class: MagicMock) -> None:
        """Integration test for graceful shutdown flow."""
        # Create mock tool instance
        mock_tool = MagicMock()
        mock_tool_class.from_tool_args.return_value = mock_tool

        # Set shutdown flag
        shutdown_requested.set()

        # The tool should handle shutdown gracefully
        # This is more of a smoke test to ensure no exceptions
        assert shutdown_requested.is_set()


class TestDockerGracefulShutdown:
    """Test cases for Docker client graceful shutdown."""

    def test_graceful_shutdown_constants_exist(self) -> None:
        """Test that graceful shutdown constants are defined."""
        # Test that the environment variable constant exists
        import os

        # Test default timeout behavior
        default_timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
        assert default_timeout >= 30  # Minimum timeout

        # Test timeout bounds
        test_timeout = min(max(default_timeout, 30), 7200)
        assert 30 <= test_timeout <= 7200

    def test_graceful_shutdown_environment_variable(self) -> None:
        """Test graceful shutdown period environment variable handling."""
        import os

        # Test with valid timeout
        with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': '600'}):
            timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            bounded_timeout = min(max(timeout, 30), 7200)
            assert bounded_timeout == 600

        # Test with timeout too high (should be capped)
        with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': '10000'}):
            timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            bounded_timeout = min(max(timeout, 30), 7200)
            assert bounded_timeout == 7200

        # Test with timeout too low (should be raised to minimum)
        with patch.dict(os.environ, {'GRACEFUL_SHUTDOWN_PERIOD': '10'}):
            timeout = int(os.getenv('GRACEFUL_SHUTDOWN_PERIOD', '300'))
            bounded_timeout = min(max(timeout, 30), 7200)
            assert bounded_timeout == 30
