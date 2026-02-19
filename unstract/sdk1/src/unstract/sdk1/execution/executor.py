"""Base executor interface for the pluggable executor framework.

All executors must subclass ``BaseExecutor`` and implement ``name``
and ``execute``.  Registration is handled by
``ExecutorRegistry.register``.
"""

from abc import ABC, abstractmethod

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.result import ExecutionResult


class BaseExecutor(ABC):
    """Abstract base class for execution strategy implementations.

    Each executor encapsulates a particular extraction strategy
    (e.g. the legacy promptservice pipeline, an agentic table
    extractor, etc.).  Executors are stateless — all request-
    specific data arrives via ``ExecutionContext``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier used to look up this executor.

        Must match the ``executor_name`` value in
        ``ExecutionContext``.  Convention: lowercase, snake_case
        (e.g. ``"legacy"``, ``"agentic_table"``).
        """

    @abstractmethod
    def execute(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Run the extraction strategy described by *context*.

        Args:
            context: Fully-populated execution context with
                operation type and executor params.

        Returns:
            An ``ExecutionResult`` whose ``data`` dict conforms to
            the response contract for the given operation.
        """
