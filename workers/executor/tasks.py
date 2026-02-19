"""Executor Worker Tasks

Defines the execute_extraction Celery task that receives an
ExecutionContext dict, runs the appropriate executor via
ExecutionOrchestrator, and returns an ExecutionResult dict.
"""

import logging

from celery import shared_task

from shared.enums.task_enums import TaskName
from shared.infrastructure.logging import WorkerLogger

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.result import ExecutionResult

logger = WorkerLogger.get_logger(__name__)


@shared_task(
    bind=True,
    name=TaskName.EXECUTE_EXTRACTION,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    retry_jitter=True,
)
def execute_extraction(
    self, execution_context_dict: dict
) -> dict:
    """Execute an extraction operation via the executor framework.

    This is the single Celery task entry point for all extraction
    operations.  Both the workflow path (structure tool task) and
    the IDE path (PromptStudioHelper) dispatch to this task.

    Args:
        execution_context_dict: Serialized ExecutionContext.

    Returns:
        Serialized ExecutionResult dict.
    """
    request_id = execution_context_dict.get("request_id", "")
    logger.info(
        "Received execute_extraction task: "
        "celery_task_id=%s request_id=%s executor=%s operation=%s",
        self.request.id,
        request_id,
        execution_context_dict.get("executor_name"),
        execution_context_dict.get("operation"),
    )

    try:
        context = ExecutionContext.from_dict(execution_context_dict)
    except (KeyError, ValueError) as exc:
        logger.error(
            "Invalid execution context: %s", exc, exc_info=True
        )
        return ExecutionResult.failure(
            error=f"Invalid execution context: {exc}"
        ).to_dict()

    orchestrator = ExecutionOrchestrator()
    result = orchestrator.execute(context)

    logger.info(
        "execute_extraction complete: "
        "celery_task_id=%s request_id=%s success=%s",
        self.request.id,
        context.request_id,
        result.success,
    )
    return result.to_dict()
