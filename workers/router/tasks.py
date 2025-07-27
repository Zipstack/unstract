"""Router Worker Tasks

Main router task that matches the existing Django backend pattern.
Routes workflow executions to specialized workers based on execution type.
This is the exact equivalent of async_execute_bin in workflow_helper.py
"""

from typing import Any

from celery import current_task

# Import shared worker infrastructure
from shared.api_client import InternalAPIClient
from shared.config import WorkerConfig

# Import from shared worker modules
from shared.constants import Account
from shared.local_context import StateStore
from shared.logging_utils import WorkerLogger, log_context, monitor_performance
from shared.retry_utils import circuit_breaker
from worker import app

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus, FileHashData

# Import common workflow utilities
from unstract.core.workflow_utils import PipelineTypeResolver

logger = WorkerLogger.get_logger(__name__)


@app.task(
    bind=True,
    name="async_execute_bin",
    autoretry_for=(Exception,),
    max_retries=0,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
@monitor_performance
def async_execute_bin(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, FileHashData],
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    use_file_history: bool = True,
    **kwargs: dict[str, Any],
) -> Any:
    """Asynchronous Execution By celery - Router Task.

    This task routes workflow executions to specialized workers based on the
    execution type. API deployments are routed to async_execute_bin_api,
    while general workflows are routed to async_execute_bin_general.

    This is the exact equivalent of the router task in workflow_helper.py

    Args:
        schema_name (str): schema name to get Data
        workflow_id (str): Workflow Id
        execution_id (str): Id of the execution
        hash_values_of_files (dict): File hash data
        scheduled (bool, optional): Represents if it is a scheduled execution
            Defaults to False
        execution_mode (Optional[tuple]): WorkflowExecution Mode
            Defaults to None
        pipeline_id (Optional[str], optional): Id of pipeline. Defaults to None
        use_file_history (bool): Use FileHistory table to return results on already
            processed files. Defaults to True

    Kwargs:
        log_events_id (str): Session ID of the user,
            helps establish WS connection for streaming logs to the FE

    Returns:
        Result from workflow execution
    """
    task_id = current_task.request.id

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
    ):
        logger.info(f"Routing execution {execution_id} for workflow {workflow_id}")

        try:
            # Set organization in state store for execution
            StateStore.set(Account.ORGANIZATION_ID, schema_name)

            # Determine execution type and route to appropriate specialized worker
            is_api_deployment = _is_api_deployment_execution(
                pipeline_id, workflow_id, schema_name
            )

            config = WorkerConfig()

            if is_api_deployment:
                logger.info(f"Routing execution {execution_id} to API deployment worker")
                # Route to API deployment worker via Celery
                result = app.send_task(
                    "async_execute_bin_api",
                    args=[
                        schema_name,
                        workflow_id,
                        execution_id,
                        hash_values_of_files,
                    ],
                    kwargs={
                        "scheduled": scheduled,
                        "execution_mode": execution_mode,
                        "pipeline_id": pipeline_id,
                        "use_file_history": use_file_history,
                        **kwargs,
                    },
                    queue="celery_api_deployments",
                )
                return result.get()
            else:
                logger.info(
                    f"Routing execution {execution_id} to general workflow worker"
                )
                # Route to general workflow worker via Celery
                result = app.send_task(
                    "async_execute_bin_general",
                    args=[
                        schema_name,
                        workflow_id,
                        execution_id,
                        hash_values_of_files,
                    ],
                    kwargs={
                        "scheduled": scheduled,
                        "execution_mode": execution_mode,
                        "pipeline_id": pipeline_id,
                        "use_file_history": use_file_history,
                        **kwargs,
                    },
                    queue="celery",
                )
                return result.get()

        except Exception as e:
            logger.error(f"Router task failed for execution {execution_id}: {e}")

            # Try to update execution status to failed
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                        attempts=self.request.retries + 1,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            # Re-raise for Celery retry mechanism
            raise


def _is_api_deployment_execution(
    pipeline_id: str | None, workflow_id: str, schema_name: str
) -> bool:
    """Determine if this execution is for an API deployment.

    Uses the improved PipelineTypeResolver for consistent detection.

    Args:
        pipeline_id: Pipeline ID (may be None)
        workflow_id: Workflow ID
        schema_name: Organization schema name

    Returns:
        True if this is an API deployment execution, False otherwise
    """
    try:
        config = WorkerConfig()

        with InternalAPIClient(config) as api_client:
            api_client.set_organization_context(schema_name)

            # Use common resolver for consistent pipeline type detection
            resolver = PipelineTypeResolver(api_client)
            should_use_api, routing_info = resolver.should_route_to_api_worker(
                pipeline_id, workflow_id
            )

            logger.info(
                f"Routing decision for execution: {routing_info['routing_reason']} "
                f"(checks: {routing_info['checks_performed']})"
            )

            return should_use_api

    except Exception as e:
        logger.warning(f"Failed to determine if execution is API deployment: {e}")
        # Default to general workflow on error
        return False


@app.task(
    bind=True,
    name="async_execute_bin_general",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=60.0)
def async_execute_bin_general(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    hash_values_of_files: dict[str, dict[str, Any]],
    scheduled: bool = False,
    execution_mode: tuple | None = None,
    pipeline_id: str | None = None,
    use_file_history: bool = True,
    **kwargs: dict[str, Any],
) -> dict[str, Any]:
    """General workflow execution worker.

    Handles non-API deployment workflow executions.

    Args:
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        hash_values_of_files: File hash data
        scheduled: Whether execution is scheduled
        execution_mode: Execution mode tuple
        pipeline_id: Pipeline ID
        use_file_history: Whether to use file history

    Returns:
        Execution result dictionary
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=schema_name,
        pipeline_id=pipeline_id,
    ):
        logger.info(
            f"Starting general workflow execution for workflow {workflow_id}, execution {execution_id}"
        )

        try:
            # Set organization context
            StateStore.set(Account.ORGANIZATION_ID, schema_name)

            # Initialize API client with organization context
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Get workflow execution context
                api_client.get_workflow_execution(execution_id)
                logger.info(f"Retrieved execution context for {execution_id}")

                # Update execution status to in progress
                api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status=ExecutionStatus.EXECUTING.value,
                    attempts=self.request.retries + 1,
                )

                # Create file batches via internal API
                batch_results = []
                if hash_values_of_files:
                    batch_results = _create_file_batches_general(
                        api_client, execution_id, hash_values_of_files, pipeline_id
                    )

                    # Now trigger file processing workers using chord pattern
                    chord_result = _orchestrate_file_processing_chord_general(
                        api_client,
                        execution_id,
                        workflow_id,
                        batch_results,
                        pipeline_id,
                        execution_mode,
                        use_file_history,
                        schema_name,
                    )

                    logger.info(
                        f"Orchestrated file processing chord for execution {execution_id}"
                    )

                    # Return chord info instead of completing immediately
                    return {
                        "status": "orchestrated",
                        "execution_id": execution_id,
                        "workflow_id": workflow_id,
                        "task_id": task_id,
                        "files_processed": len(hash_values_of_files),
                        "batch_results": batch_results,
                        "chord_id": chord_result.get("chord_id"),
                        "message": "File processing orchestrated, waiting for completion",
                    }
                else:
                    # No files to process, complete immediately
                    # Don't send total_files=0 for empty workflows to avoid overwriting
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.COMPLETED.value,
                        execution_time=0,
                    )

                    return {
                        "status": "completed",
                        "execution_id": execution_id,
                        "workflow_id": workflow_id,
                        "task_id": task_id,
                        "files_processed": 0,
                        "message": "No files to process",
                    }

        except Exception as e:
            logger.error(f"General workflow execution failed for {execution_id}: {e}")

            # Try to update execution status to failed
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                        attempts=self.request.retries + 1,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            # Re-raise for Celery retry mechanism
            raise


def _create_file_batches_general(
    api_client: InternalAPIClient,
    execution_id: str,
    hash_values_of_files: dict[str, dict[str, Any]],
    pipeline_id: str | None = None,
) -> list:
    """Create file batches for general workflow execution.

    Args:
        api_client: Internal API client
        execution_id: Execution ID
        hash_values_of_files: File hash data
        pipeline_id: Pipeline ID

    Returns:
        List of file batch results
    """
    logger.info(
        f"Processing {len(hash_values_of_files)} files for execution {execution_id}"
    )

    try:
        # Convert hash values to file data format expected by API
        files_data = []
        for file_key, file_hash_data in hash_values_of_files.items():
            # Convert UUID objects to strings if present
            provider_file_uuid = file_hash_data.get("provider_file_uuid")
            if provider_file_uuid and hasattr(provider_file_uuid, "hex"):
                provider_file_uuid = str(provider_file_uuid)

            file_data = {
                "file_name": file_hash_data.get("file_name", file_key),
                "file_path": file_hash_data.get("file_path"),
                "file_size": file_hash_data.get("file_size"),
                "file_hash": file_hash_data.get("file_hash"),
                "provider_file_uuid": provider_file_uuid,
                "mime_type": file_hash_data.get("mime_type"),
                "fs_metadata": file_hash_data.get("fs_metadata", {}),
            }
            files_data.append(file_data)

        # Create file batch via internal API
        batch_response = api_client.create_file_batch(
            workflow_execution_id=execution_id,
            files=files_data,
            is_api=False,  # This is for general workflows
        )

        logger.info(
            f"Created file batch {batch_response.get('batch_id')} with {batch_response.get('total_files')} files"
        )

        return [batch_response]

    except Exception as e:
        logger.error(f"Failed to process file batches: {e}")
        raise


def _orchestrate_file_processing_chord_general(
    api_client: InternalAPIClient,
    execution_id: str,
    workflow_id: str,
    batch_results: list,
    pipeline_id: str | None,
    execution_mode: tuple | None,
    use_file_history: bool,
    schema_name: str,
) -> dict[str, Any]:
    """Orchestrate file processing using Celery chord pattern for general workflows.

    Creates file processing tasks and sets up callback for completion.

    Args:
        api_client: Internal API client
        execution_id: Execution ID
        workflow_id: Workflow ID
        batch_results: File batch creation results
        pipeline_id: Pipeline ID
        execution_mode: Execution mode
        use_file_history: Whether to use file history
        schema_name: Organization schema name

    Returns:
        Chord orchestration result
    """
    from celery import chord

    logger.info(f"Orchestrating file processing chord for {len(batch_results)} batches")

    try:
        # Create file processing tasks for each batch
        file_processing_tasks = []

        for batch_result in batch_results:
            batch_id = batch_result.get("batch_id")
            created_files = batch_result.get("created_file_executions", [])

            logger.info(
                f"Creating file processing task for batch {batch_id} with {len(created_files)} files"
            )

            # Create task signature for file processing
            task_signature = app.signature(
                "process_file_batch",
                args=[
                    schema_name,
                    workflow_id,
                    execution_id,
                    batch_id,
                    created_files,
                    pipeline_id,
                    execution_mode,
                    use_file_history,
                ],
                queue="file_processing",  # Regular file processing queue
            )

            file_processing_tasks.append(task_signature)

        # Create callback task signature
        callback_signature = app.signature(
            "process_batch_callback",
            args=[
                schema_name,
                workflow_id,
                execution_id,
                len(batch_results),
                pipeline_id,
            ],
            queue="file_processing_callback",  # Regular callback queue
        )

        # Execute chord: file processing tasks → callback
        chord_result = chord(file_processing_tasks)(callback_signature)

        logger.info(f"Chord orchestrated with ID: {chord_result.id}")

        return {
            "chord_id": chord_result.id,
            "file_processing_tasks": len(file_processing_tasks),
            "status": "orchestrated",
        }

    except Exception as e:
        logger.error(f"Failed to orchestrate file processing chord: {e}")
        raise
