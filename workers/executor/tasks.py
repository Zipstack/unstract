"""Executor Worker Tasks

Defines the execute_extraction Celery task that receives an
ExecutionContext dict, runs the appropriate executor via
ExecutionOrchestrator, and returns an ExecutionResult dict.
"""

from celery import shared_task
from shared.clients import UsageAPIClient
from shared.enums.task_enums import TaskName
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import WorkerLogger

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.result import ExecutionResult

logger = WorkerLogger.get_logger(__name__)

_LLM_BEARING_OPS = frozenset(
    {
        "answer_prompt",
        "single_pass_extraction",
        "summarize",
        "structure_pipeline",
    }
)


@shared_task(
    bind=True,
    name=TaskName.EXECUTE_EXTRACTION,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    retry_jitter=True,
)
def execute_extraction(self, execution_context_dict: dict) -> dict:
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
        "celery_task_id=%s request_id=%s executor=%s "
        "operation=%s execution_source=%s run_id=%s",
        self.request.id,
        request_id,
        execution_context_dict.get("executor_name"),
        execution_context_dict.get("operation"),
        execution_context_dict.get("execution_source"),
        execution_context_dict.get("run_id"),
    )

    try:
        context = ExecutionContext.from_dict(execution_context_dict)
    except (KeyError, ValueError) as exc:
        logger.error("Invalid execution context: %s", exc, exc_info=True)
        return ExecutionResult.failure(
            error=f"Invalid execution context: {exc}"
        ).to_dict()

    # Build component dict for log correlation when streaming to
    # the frontend.  Attached as a transient attribute (not serialized).
    if context.log_events_id:
        params = context.executor_params
        # For compound operations, extract nested params for log
        # correlation.
        if context.operation == "ide_index":
            index_params = params.get("index_params", {})
            extract_params = params.get("extract_params", {})
            usage_kwargs = extract_params.get("usage_kwargs", {})
            context._log_component = {
                "tool_id": index_params.get("tool_id", ""),
                "run_id": context.run_id,
                "doc_name": str(usage_kwargs.get("file_name", "")),
                "operation": context.operation,
            }
        elif context.operation == "structure_pipeline":
            answer_params = params.get("answer_params", {})
            pipeline_opts = params.get("pipeline_options", {})
            context._log_component = {
                "tool_id": answer_params.get("tool_id", ""),
                "run_id": context.run_id,
                "doc_name": str(pipeline_opts.get("source_file_name", "")),
                "operation": context.operation,
            }
        else:
            context._log_component = {
                "tool_id": params.get("tool_id", ""),
                "run_id": context.run_id,
                "doc_name": str(params.get("file_name", "")),
                "operation": context.operation,
            }
    else:
        context._log_component = {}

    orchestrator = ExecutionOrchestrator()
    result = orchestrator.execute(context)

    usage_records = result.metadata.get("usage_records", [])
    if usage_records:
        try:
            config = WorkerConfig()
            with UsageAPIClient(config) as usage_client:
                # Org context is set on the client; no need to pass it per call.
                usage_client.set_organization_context(context.organization_id)
                ok = usage_client.bulk_create_usage(usage_records)
            if not ok:
                # ERROR severity so dropped billing rows are recoverable from logs.
                logger.error(
                    "bulk_create_usage returned failure for %d records "
                    "(run_id=%s organization_id=%s)",
                    len(usage_records),
                    context.run_id,
                    context.organization_id,
                )
        except Exception:
            logger.error(
                "Failed to flush %d usage records for run_id=%s organization_id=%s",
                len(usage_records),
                context.run_id,
                context.organization_id,
                exc_info=True,
            )
    elif result.success and context.operation in _LLM_BEARING_OPS:
        logger.info(
            "No usage_records emitted for op=%s run_id=%s organization_id=%s "
            "(unexpected for an LLM-bearing operation)",
            context.operation,
            context.run_id,
            context.organization_id,
        )

    logger.info(
        "execute_extraction complete: celery_task_id=%s request_id=%s success=%s",
        self.request.id,
        context.request_id,
        result.success,
    )

    return result.to_dict()
