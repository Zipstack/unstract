"""Unstract AutoGen Client Package.

A Python package that provides a ChatCompletionClient implementation for Microsoft AutoGen framework,
using Unstract LLM adapters as the backend for LLM interactions.
"""

__version__ = "0.1.0"

from .client import UnstractAutoGenClient
from .exceptions import (
    UnstractAutoGenError,
    UnstractCompletionError,
    UnstractConfigurationError,
)
from .helper import (
    SimpleAutoGenAgent,
    create_simple_autogen_agent,
    process_with_autogen,
    process_with_autogen_async,
    run_autogen_poc,
)

__all__ = [
    "UnstractAutoGenClient",
    "UnstractAutoGenError",
    "UnstractConfigurationError",
    "UnstractCompletionError",
    "SimpleAutoGenAgent",
    "create_simple_autogen_agent",
    "process_with_autogen",
    "process_with_autogen_async",
    "run_autogen_poc",
]
