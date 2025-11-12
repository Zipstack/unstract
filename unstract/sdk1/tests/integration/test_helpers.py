"""Helper utilities for integration tests.

This module provides common helper functions and utilities for integration tests
across different adapter types.
"""

import json
import os
import time
from typing import Any


class TestHelpers:
    """Helper class for integration test utilities."""

    @staticmethod
    def verify_response_schema(
        response: dict[str, Any], required_fields: list[str]
    ) -> bool:
        """Verify that a response contains all required fields.

        Args:
            response: The response dictionary to verify
            required_fields: List of required field names

        Returns:
            bool: True if all required fields are present, False otherwise
        """
        for field in required_fields:
            if field not in response:
                return False
        return True

    @staticmethod
    def verify_json_structure(text: str) -> bool:
        """Verify that text contains valid JSON structure.

        Args:
            text: The text to check for JSON

        Returns:
            bool: True if text contains valid JSON, False otherwise
        """
        try:
            # Try to extract JSON from text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                # Try array format
                start = text.find("[")
                end = text.rfind("]") + 1
                if start == -1 or end == 0:
                    return False

            json_str = text[start:end]
            json.loads(json_str)
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    @staticmethod
    def retry_with_backoff(
        func: callable,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> Any:
        """Retry a function with exponential backoff.

        Args:
            func: Function to retry
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay on each retry

        Returns:
            The result of the function call

        Raises:
            The last exception if all retries fail
        """
        delay = initial_delay
        last_exception = None

        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    print(f"   Retry attempt {attempt + 1}/{max_retries} after {delay}s")
                    time.sleep(delay)
                    delay *= backoff_factor

        raise last_exception

    @staticmethod
    def load_test_env_vars(env_file: str = ".env.test") -> dict[str, str]:
        """Load test environment variables from file.

        Args:
            env_file: Path to environment file

        Returns:
            Dictionary of environment variables
        """
        env_vars = {}
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip().strip('"').strip("'")
        return env_vars

    @staticmethod
    def check_required_env_vars(required_vars: list[str]) -> tuple[bool, list[str]]:
        """Check if all required environment variables are set.

        Args:
            required_vars: List of required environment variable names

        Returns:
            Tuple of (all_present: bool, missing_vars: list[str])
        """
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        return (len(missing_vars) == 0, missing_vars)

    @staticmethod
    def measure_execution_time(func: callable) -> tuple[Any, float]:
        """Measure the execution time of a function.

        Args:
            func: Function to measure

        Returns:
            Tuple of (result, execution_time_seconds)
        """
        start_time = time.time()
        result = func()
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time

    @staticmethod
    def verify_token_count_reasonable(
        text: str, expected_min: int = 1, expected_max: int = 10000
    ) -> bool:
        """Verify that text token count is within reasonable bounds.

        Args:
            text: Text to check
            expected_min: Minimum expected tokens (rough estimate)
            expected_max: Maximum expected tokens (rough estimate)

        Returns:
            bool: True if token count appears reasonable
        """
        # Rough estimate: 1 token ~= 4 characters
        estimated_tokens = len(text) // 4
        return expected_min <= estimated_tokens <= expected_max

    @staticmethod
    def sanitize_response_for_logging(response: str, max_length: int = 200) -> str:
        """Sanitize response text for safe logging.

        Args:
            response: Response text to sanitize
            max_length: Maximum length for logged response

        Returns:
            Sanitized response string
        """
        # Remove any potential sensitive data patterns
        sanitized = response[:max_length]
        if len(response) > max_length:
            sanitized += "..."
        return sanitized

    @staticmethod
    def create_mock_platform_context() -> dict[str, Any]:
        """Create a mock platform context for testing.

        Returns:
            Dictionary with mock platform context data
        """
        return {
            "organization_id": "test-org-id",
            "user_id": "test-user-id",
            "workflow_id": "test-workflow-id",
            "execution_id": "test-execution-id",
        }

    @staticmethod
    def validate_error_message(error_message: str, expected_keywords: list[str]) -> bool:
        """Validate that error message contains expected keywords.

        Args:
            error_message: The error message to validate
            expected_keywords: List of keywords that should appear in the error

        Returns:
            bool: True if any expected keyword is found in the error message
        """
        error_lower = error_message.lower()
        return any(keyword.lower() in error_lower for keyword in expected_keywords)


class PerformanceBenchmark:
    """Helper class for performance benchmarking in tests."""

    def __init__(self, operation_name: str):
        """Initialize benchmark.

        Args:
            operation_name: Name of the operation being benchmarked
        """
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        """Start benchmark."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End benchmark and print results."""
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        print(f"⏱️  {self.operation_name} took {duration:.2f} seconds")

    def get_duration(self) -> float:
        """Get benchmark duration.

        Returns:
            Duration in seconds, or None if not yet complete
        """
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
