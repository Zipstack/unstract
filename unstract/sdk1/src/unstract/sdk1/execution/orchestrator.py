"""Execution orchestrator for the executor worker.

The orchestrator is the entry point called by the
``execute_extraction`` Celery task.  It resolves the correct
executor from the registry and delegates execution, ensuring
that unhandled exceptions are always wrapped in a failed
``ExecutionResult``.
"""

import logging
import time

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult

logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    """Looks up and invokes the executor for a given context.

    Usage (inside the Celery task)::

        orchestrator = ExecutionOrchestrator()
        result = orchestrator.execute(context)
    """

    def execute(
        self, context: ExecutionContext
    ) -> ExecutionResult:
        """Resolve the executor and run it.

        Args:
            context: Fully-populated execution context.

        Returns:
            ``ExecutionResult`` — always, even on unhandled
            exceptions (wrapped as a failure result).
        """
        logger.info(
            "Orchestrating execution: executor=%s operation=%s "
            "run_id=%s request_id=%s",
            context.executor_name,
            context.operation,
            context.run_id,
            context.request_id,
        )

        start = time.monotonic()
        try:
            executor = ExecutorRegistry.get(context.executor_name)
        except KeyError as exc:
            logger.error("Executor lookup failed: %s", exc)
            return ExecutionResult.failure(error=str(exc))

        try:
            result = executor.execute(context)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception(
                "Executor %r raised an unhandled exception "
                "after %.2fs",
                context.executor_name,
                elapsed,
            )
            return ExecutionResult.failure(
                error=f"{type(exc).__name__}: {exc}",
                metadata={"elapsed_seconds": round(elapsed, 3)},
            )

        elapsed = time.monotonic() - start
        logger.info(
            "Execution completed: executor=%s operation=%s "
            "success=%s elapsed=%.2fs",
            context.executor_name,
            context.operation,
            result.success,
            elapsed,
        )
        return result
