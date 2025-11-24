"""Threading service for long-running operations with WebSocket progress tracking."""

import logging
import threading
import uuid
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ThreadingService:
    """Manages background threads for long-running operations."""

    _active_threads: Dict[str, threading.Thread] = {}
    _thread_results: Dict[str, Any] = {}
    _thread_errors: Dict[str, str] = {}

    @classmethod
    def run_in_background(
        cls,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        Run a function in a background thread.

        Args:
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            thread_id: Optional custom thread ID (auto-generated if not provided)

        Returns:
            thread_id: Unique identifier for tracking
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        kwargs = kwargs or {}

        def wrapper():
            try:
                logger.info(f"Starting background thread {thread_id}: {func.__name__}")
                result = func(*args, **kwargs)
                logger.info(f"Background thread {thread_id} completed successfully")

                # Store result
                cls._thread_results[thread_id] = result

            except Exception as e:
                logger.error(f"Background thread {thread_id} failed: {e}", exc_info=True)

                # Store error
                cls._thread_errors[thread_id] = str(e)

            finally:
                # Cleanup thread from active list
                cls._active_threads.pop(thread_id, None)

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        cls._active_threads[thread_id] = thread

        logger.info(f"Started background thread {thread_id}")
        return thread_id

    @classmethod
    def get_thread_status(cls, thread_id: str) -> Dict[str, Any]:
        """
        Get status of a background thread.

        Args:
            thread_id: Thread identifier

        Returns:
            Status dictionary with keys: status, thread_id, result, error
        """
        thread = cls._active_threads.get(thread_id)

        if thread and thread.is_alive():
            return {
                "status": "running",
                "thread_id": thread_id,
            }

        # Thread completed or doesn't exist
        if thread_id in cls._thread_results:
            result = cls._thread_results.pop(thread_id)
            return {
                "status": "complete",
                "thread_id": thread_id,
                "result": result,
            }

        if thread_id in cls._thread_errors:
            error = cls._thread_errors.pop(thread_id)
            return {
                "status": "error",
                "thread_id": thread_id,
                "error": error,
            }

        return {
            "status": "not_found",
            "thread_id": thread_id,
        }

    @classmethod
    def is_thread_running(cls, thread_id: str) -> bool:
        """Check if a thread is still running."""
        thread = cls._active_threads.get(thread_id)
        return thread is not None and thread.is_alive()

    @classmethod
    def wait_for_thread(cls, thread_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Wait for a thread to complete.

        Args:
            thread_id: Thread identifier
            timeout: Optional timeout in seconds

        Returns:
            Thread status after completion or timeout
        """
        thread = cls._active_threads.get(thread_id)

        if thread:
            thread.join(timeout=timeout)

        return cls.get_thread_status(thread_id)

    @classmethod
    def cleanup_completed_threads(cls):
        """Remove completed threads from tracking."""
        completed_ids = []

        for thread_id, thread in cls._active_threads.items():
            if not thread.is_alive():
                completed_ids.append(thread_id)

        for thread_id in completed_ids:
            cls._active_threads.pop(thread_id, None)

        logger.info(f"Cleaned up {len(completed_ids)} completed threads")
