"""ExecutorToolShim — Lightweight BaseTool substitute for executor workers.

Adapters (PlatformHelper, LLM, Embedding, VectorDB, X2Text) all require
a ``tool: BaseTool`` parameter that provides ``get_env_or_die()`` and
``stream_log()``.  The executor worker has no ``BaseTool`` instance, so
this shim provides just those two methods.

Precedent: ``prompt-service/.../helpers/prompt_ide_base_tool.py``
(``PromptServiceBaseTool``).
"""

import logging
import os
from typing import Any

from unstract.sdk1.constants import LogLevel, ToolEnv
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.tool.stream import StreamMixin

logger = logging.getLogger(__name__)

# Mapping from SDK LogLevel enum to Python logging levels.
_LEVEL_MAP = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARN: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.FATAL: logging.CRITICAL,
}


class ExecutorToolShim(StreamMixin):
    """Minimal BaseTool substitute for use inside executor workers.

    Provides the two methods that adapters actually call:

    - ``get_env_or_die(env_key)`` — reads env vars, with special
      handling for ``PLATFORM_SERVICE_API_KEY`` (multitenancy)
    - ``stream_log(log, level)`` — routes to Python logging instead
      of the Unstract stdout JSON protocol used by tools

    Usage::

        shim = ExecutorToolShim(platform_api_key="sk-...")
        adapter = SomeAdapter(tool=shim)  # adapter calls shim.get_env_or_die()
    """

    def __init__(self, platform_api_key: str = "") -> None:
        """Initialize the shim.

        Args:
            platform_api_key: The platform service API key for this
                execution.  Returned by ``get_env_or_die()`` when the
                caller asks for ``PLATFORM_SERVICE_API_KEY``.
        """
        self.platform_api_key = platform_api_key
        # Initialize StreamMixin.  EXECUTION_BY_TOOL is not set in
        # the worker environment, so _exec_by_tool will be False.
        super().__init__(log_level=LogLevel.INFO)

    def get_env_or_die(self, env_key: str) -> str:
        """Return environment variable value.

        Special-cases ``PLATFORM_SERVICE_API_KEY`` to return the key
        passed at construction time (supports multitenancy — each
        execution may use a different org's API key).

        Args:
            env_key: Environment variable name.

        Returns:
            The value of the environment variable.

        Raises:
            SdkError: If the variable is missing or empty.
        """
        if env_key == ToolEnv.PLATFORM_API_KEY:
            if not self.platform_api_key:
                raise SdkError(
                    f"Env variable '{env_key}' is required"
                )
            return self.platform_api_key

        env_value = os.environ.get(env_key)
        if env_value is None or env_value == "":
            raise SdkError(
                f"Env variable '{env_key}' is required"
            )
        return env_value

    def stream_log(
        self,
        log: str,
        level: LogLevel = LogLevel.INFO,
        stage: str = "TOOL_RUN",
        **kwargs: dict[str, Any],
    ) -> None:
        """Route log messages to Python logging.

        In the executor worker context, logs go through the standard
        Python logging framework (captured by Celery) rather than the
        Unstract stdout JSON protocol used by tools.

        Args:
            log: The log message.
            level: SDK log level.
            stage: Ignored (only meaningful for stdout protocol).
            **kwargs: Ignored (only meaningful for stdout protocol).
        """
        py_level = _LEVEL_MAP.get(level, logging.INFO)
        logger.log(py_level, log)

    def stream_error_and_exit(
        self, message: str, err: Exception | None = None
    ) -> None:
        """Log error and raise SdkError.

        Unlike the base StreamMixin which may call ``sys.exit(1)``
        when running as a tool, the executor worker always raises
        an exception so the Celery task can handle it gracefully.

        Args:
            message: Error description.
            err: Original exception, if any.

        Raises:
            SdkError: Always.
        """
        logger.error(message)
        raise SdkError(message, actual_err=err)
