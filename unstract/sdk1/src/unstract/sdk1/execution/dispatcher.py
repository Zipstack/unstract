"""Execution dispatcher for sending Celery tasks to executor workers.

The dispatcher is the caller-side component used by both:
- Structure tool Celery task (workflow path)
- PromptStudioHelper (IDE path)

It sends ``execute_extraction`` tasks to the ``executor`` queue
and waits for results via ``AsyncResult.get()``.
"""

import logging
import os
from typing import Any

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.result import ExecutionResult

logger = logging.getLogger(__name__)

# Constants matching workers/shared/enums values.
# Defined here to avoid an SDK1 → workers package dependency.
_TASK_NAME = "execute_extraction"
_QUEUE_NAME = "executor"

# Caller-side timeout (seconds) for AsyncResult.get().
# This controls how long the *caller* waits for the executor to
# finish — distinct from the executor worker's
# ``EXECUTOR_TASK_TIME_LIMIT`` which controls how long the
# *worker* allows a task to run.
#
# Resolution order (matches workers convention):
#   1. Explicit ``timeout`` parameter on dispatch()
#   2. ``EXECUTOR_RESULT_TIMEOUT`` env var
#   3. Hardcoded default (3600s)
#
# The default (3600s) is intentionally <= the executor worker's
# ``task_time_limit`` default (also 3600s) so the caller never
# waits longer than the worker allows the task to run.
_DEFAULT_TIMEOUT_ENV = "EXECUTOR_RESULT_TIMEOUT"
_DEFAULT_TIMEOUT = 3600  # 1 hour — matches executor worker default


class ExecutionDispatcher:
    """Dispatches execution to executor worker via Celery task.

    Usage::

        dispatcher = ExecutionDispatcher(celery_app=app)
        result = dispatcher.dispatch(context, timeout=120)

    Or fire-and-forget::

        task_id = dispatcher.dispatch_async(context)
    """

    def __init__(self, celery_app: Any = None) -> None:
        """Initialize the dispatcher.

        Args:
            celery_app: A Celery application instance.  Required
                for dispatching tasks.  Can be ``None`` only if
                set later via ``celery_app`` attribute.
        """
        self._app = celery_app

    def dispatch(
        self,
        context: ExecutionContext,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """Dispatch context as a Celery task and wait for result.

        Args:
            context: ExecutionContext to dispatch.
            timeout: Max seconds to wait.  ``None`` reads from
                the ``EXECUTOR_RESULT_TIMEOUT`` env var,
                falling back to 3600s.

        Returns:
            ExecutionResult from the executor.

        Raises:
            ValueError: If no Celery app is configured.
        """
        if self._app is None:
            raise ValueError(
                "No Celery app configured on ExecutionDispatcher"
            )

        if timeout is None:
            timeout = int(
                os.environ.get(
                    _DEFAULT_TIMEOUT_ENV, _DEFAULT_TIMEOUT
                )
            )

        logger.info(
            "Dispatching execution: executor=%s operation=%s "
            "run_id=%s request_id=%s timeout=%ss",
            context.executor_name,
            context.operation,
            context.run_id,
            context.request_id,
            timeout,
        )

        async_result = self._app.send_task(
            _TASK_NAME,
            args=[context.to_dict()],
            queue=_QUEUE_NAME,
        )
        logger.info(
            "Task sent: celery_task_id=%s, waiting for result...",
            async_result.id,
        )

        try:
            # disable_sync_subtasks=False: safe because the executor task
            # runs on a separate worker pool (worker-v2) — no deadlock
            # risk even when dispatch() is called from inside a Django
            # Celery task.
            result_dict = async_result.get(
                timeout=timeout,
                disable_sync_subtasks=False,
            )
        except Exception as exc:
            logger.error(
                "Dispatch failed: executor=%s operation=%s "
                "run_id=%s error=%s",
                context.executor_name,
                context.operation,
                context.run_id,
                exc,
            )
            return ExecutionResult.failure(
                error=f"{type(exc).__name__}: {exc}",
            )

        return ExecutionResult.from_dict(result_dict)

    def dispatch_async(
        self,
        context: ExecutionContext,
    ) -> str:
        """Dispatch without waiting.  Returns task_id for polling.

        Args:
            context: ExecutionContext to dispatch.

        Returns:
            The Celery task ID (use with ``AsyncResult`` to poll).

        Raises:
            ValueError: If no Celery app is configured.
        """
        if self._app is None:
            raise ValueError(
                "No Celery app configured on ExecutionDispatcher"
            )

        logger.info(
            "Dispatching async execution: executor=%s "
            "operation=%s run_id=%s request_id=%s",
            context.executor_name,
            context.operation,
            context.run_id,
            context.request_id,
        )

        async_result = self._app.send_task(
            _TASK_NAME,
            args=[context.to_dict()],
            queue=_QUEUE_NAME,
        )
        return async_result.id
