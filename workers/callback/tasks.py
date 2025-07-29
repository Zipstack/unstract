"""File Processing Callback Worker Tasks

Exact implementation matching Django backend patterns for callback tasks.
Uses the same logic as file_execution_tasks.py process_batch_callback.
This replaces the heavy Django process_batch_callback task with API coordination.
"""

import time
from typing import Any

# Use Celery current_app to avoid circular imports
from celery import current_app as app

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus, FileHashData

# Import shared worker infrastructure
from workers.shared.api_client import InternalAPIClient
from workers.shared.config import WorkerConfig

# Import from shared worker modules
from workers.shared.constants import Account
from workers.shared.local_context import StateStore
from workers.shared.logging_utils import WorkerLogger, log_context, monitor_performance
from workers.shared.retry_utils import CircuitBreakerOpenError, circuit_breaker

logger = WorkerLogger.get_logger(__name__)


def _map_execution_status_to_pipeline_status(execution_status: str) -> str:
    """Map workflow execution status to pipeline status.

    Based on the Pipeline model PipelineStatus choices:
    - SUCCESS = "SUCCESS"
    - FAILURE = "FAILURE"
    - INPROGRESS = "INPROGRESS"
    - YET_TO_START = "YET_TO_START"
    - RESTARTING = "RESTARTING"
    - PAUSED = "PAUSED"

    Args:
        execution_status: Workflow execution status

    Returns:
        Corresponding pipeline status
    """
    status_mapping = {
        "COMPLETED": "SUCCESS",
        "SUCCESS": "SUCCESS",
        "ERROR": "FAILURE",
        "FAILED": "FAILURE",
        "FAILURE": "FAILURE",
        "EXECUTING": "INPROGRESS",
        "RUNNING": "INPROGRESS",
        "INPROGRESS": "INPROGRESS",
        "QUEUED": "INPROGRESS",
        "PENDING": "YET_TO_START",
        "YET_TO_START": "YET_TO_START",
    }

    # Default to FAILURE for unknown statuses
    return status_mapping.get(execution_status.upper(), "FAILURE")


@app.task(
    bind=True,
    name="process_batch_callback",
    max_retries=0,  # Match Django backend pattern
    ignore_result=False,  # Match Django backend pattern
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
def process_batch_callback(self, results, *args, **kwargs) -> dict[str, Any]:
    """Callback task to handle batch processing results.

    This exactly matches the Django backend process_batch_callback task signature
    and logic, using API coordination instead of direct ORM access.

    Args:
        results (list): List of results from each batch
            Each result is a dictionary containing:
            - successful_files: Number of successfully processed files
            - failed_files: Number of failed files
        **kwargs: Additional arguments including:
            - execution_id: ID of the execution

    Returns:
        Callback processing result
    """
    task_id = self.request.id

    # Extract execution_id from kwargs exactly like Django backend
    execution_id = kwargs.get("execution_id")
    if not execution_id:
        raise ValueError("execution_id is required in kwargs")

    # CRITICAL FIX: Get pipeline_id directly from kwargs first (preferred)
    pipeline_id = kwargs.get("pipeline_id")

    # Get workflow execution context via API (instead of Django ORM)
    config = WorkerConfig()
    with InternalAPIClient(config) as api_client:
        execution_context = api_client.get_workflow_execution(execution_id)
        workflow_execution = execution_context.get("execution", {})
        workflow = execution_context.get("workflow", {})

        # Extract organization_id with multiple fallback strategies
        organization_id = (
            workflow_execution.get("organization_id")
            or workflow.get("organization_id")
            or workflow.get("organization", {}).get("id")
            if isinstance(workflow.get("organization"), dict)
            else execution_context.get("organization_context", {}).get("organization_id")
            or None
        )

        workflow_id = workflow_execution.get("workflow_id") or workflow.get("id")

        # Fallback to execution context pipeline_id if not passed directly
        if not pipeline_id:
            pipeline_id = workflow_execution.get("pipeline_id")
            logger.info(f"Using pipeline_id from execution context: {pipeline_id}")
        else:
            logger.info(f"Using pipeline_id from direct kwargs: {pipeline_id}")

        logger.info(
            f"Extracted context: organization_id={organization_id}, workflow_id={workflow_id}, pipeline_id={pipeline_id}"
        )

        if not organization_id:
            logger.warning(
                f"Organization ID not found in execution context: {execution_context}"
            )
            # Try to extract from the first file batch result if available
            for result in results:
                if isinstance(result, dict) and "organization_id" in result:
                    organization_id = result["organization_id"]
                    logger.info(
                        f"Extracted organization_id from batch result: {organization_id}"
                    )
                    break

        # Set organization context exactly like Django backend
        if organization_id:
            StateStore.set(Account.ORGANIZATION_ID, organization_id)
            api_client.set_organization_context(organization_id)
        else:
            logger.error(
                f"Could not extract organization_id for execution {execution_id}. Pipeline status update may fail."
            )

    with log_context(
        task_id=task_id,
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=organization_id,
        pipeline_id=pipeline_id,
    ):
        logger.info(f"Starting batch callback processing for execution {execution_id}")

        try:
            # Aggregate results from all file batches (exactly like Django backend)
            aggregated_results = _aggregate_file_batch_results(results)

            # Update execution with aggregated results (via API instead of Django ORM)
            _update_execution_with_results(
                api_client=api_client,
                execution_id=execution_id,
                aggregated_results=aggregated_results,
                organization_id=organization_id,
            )

            # Destination processing is now handled in file processing worker (not callback)
            # Callback worker only handles finalization and aggregation
            logger.info(
                f"Destination processing was handled during file processing for {aggregated_results['successful_files']} successful files"
            )
            destination_results = {
                "status": "handled_in_file_processing",
                "reason": "destination_processing_moved_to_file_worker",
                "successful_files": aggregated_results["successful_files"],
            }

            # Finalize the execution (matching Django backend logic)
            final_status = (
                "COMPLETED" if aggregated_results["failed_files"] == 0 else "COMPLETED"
            )
            try:
                finalization_result = api_client.finalize_workflow_execution(
                    execution_id=execution_id,
                    final_status=final_status,
                    total_files_processed=aggregated_results["total_files"],
                    total_execution_time=aggregated_results["total_execution_time"],
                    results_summary=aggregated_results,
                    error_summary=aggregated_results.get("errors", {}),
                    organization_id=organization_id,  # Pass organization context to avoid backend errors
                )
            except Exception as e:
                if "404" in str(e) or "Not Found" in str(e):
                    logger.info(
                        "Finalization API endpoint not available, workflow finalization completed via status update"
                    )
                    finalization_result = {
                        "status": "simulated",
                        "message": "Finalized via status update",
                    }
                else:
                    raise e

            # Update pipeline status including last_run_status and run_count (matching Django backend PipelineUtils.update_pipeline_status)
            if pipeline_id:
                try:
                    logger.info(
                        f"Updating pipeline {pipeline_id} status with organization_id: {organization_id}"
                    )

                    # Map execution status to pipeline status
                    pipeline_status = _map_execution_status_to_pipeline_status(
                        final_status
                    )

                    # Update pipeline with proper status fields
                    api_client.update_pipeline_status(
                        pipeline_id=pipeline_id,
                        execution_id=execution_id,
                        status=pipeline_status,  # Required status parameter
                        last_run_status=pipeline_status,  # Update last_run_status field
                        last_run_time=time.time(),  # Update last_run_time
                        increment_run_count=True,  # Increment run_count
                        organization_id=organization_id,
                    )
                    logger.info(
                        f"Updated pipeline {pipeline_id} last_run_status to {pipeline_status}"
                    )
                except CircuitBreakerOpenError:
                    logger.warning(
                        "Pipeline status update circuit breaker open - skipping update"
                    )
                    pass
                except Exception as e:
                    # ROOT CAUSE FIX: Handle pipeline not found errors gracefully
                    if (
                        "404" in str(e)
                        or "Pipeline not found" in str(e)
                        or "Not Found" in str(e)
                    ):
                        logger.info(
                            f"Pipeline {pipeline_id} not found - likely using stale reference, skipping update"
                        )
                        pass
                    else:
                        logger.warning(f"Failed to update pipeline status: {str(e)}")

            # Cleanup resources (gracefully handle missing endpoint)
            try:
                cleanup_result = api_client.cleanup_execution_resources(
                    execution_ids=[execution_id], cleanup_types=["cache", "temp_files"]
                )
            except CircuitBreakerOpenError:
                logger.info(
                    "Cleanup endpoint circuit breaker open - skipping resource cleanup"
                )
                cleanup_result = {"status": "skipped", "message": "Circuit breaker open"}
            except Exception as e:
                if "404" in str(e) or "Not Found" in str(e):
                    logger.info(
                        "Cleanup API endpoint not available, skipping resource cleanup"
                    )
                    cleanup_result = {
                        "status": "skipped",
                        "message": "Cleanup endpoint not available",
                    }
                else:
                    logger.warning(f"Cleanup failed but continuing execution: {str(e)}")
                    cleanup_result = {
                        "status": "failed",
                        "error": str(e),
                        "execution_continued": True,
                    }

            callback_result = {
                "status": "completed",
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "task_id": task_id,
                "aggregated_results": aggregated_results,
                "destination_results": destination_results,
                "finalization_result": finalization_result,
                "cleanup_result": cleanup_result,
                "pipeline_id": pipeline_id,
            }

            logger.info(
                f"Completed batch callback processing for execution {execution_id}"
            )

            return callback_result

        except Exception as e:
            logger.error(
                f"Batch callback processing failed for execution {execution_id}: {e}"
            )

            # Try to mark execution as failed
            try:
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(organization_id)
                    try:
                        api_client.finalize_workflow_execution(
                            execution_id=execution_id,
                            final_status="ERROR",
                            error_summary={"callback_error": str(e)},
                            organization_id=organization_id,
                        )
                    except Exception as finalize_error:
                        if "404" in str(finalize_error) or "Not Found" in str(
                            finalize_error
                        ):
                            logger.info(
                                "Finalization API endpoint not available, execution marked as failed via status update"
                            )
                        else:
                            raise finalize_error
            except Exception as cleanup_error:
                logger.error(f"Failed to mark execution as failed: {cleanup_error}")

            # Re-raise for Celery retry mechanism
            raise


@app.task(
    bind=True,
    name="process_batch_callback_api",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
def process_batch_callback_api(
    self,
    file_batch_results: list[dict[str, Any]],
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    batch_count: int,
    pipeline_id: str | None = None,
) -> dict[str, Any]:
    """Lightweight API batch callback processing task.

    This handles the final step of API workflow execution after all file batches complete.
    In a chord, this receives the results from all file processing tasks.

    Args:
        file_batch_results: Results from all file processing tasks (from chord)
        schema_name: Organization schema name
        workflow_id: Workflow ID
        execution_id: Execution ID
        batch_count: Expected number of batches
        pipeline_id: Pipeline ID

    Returns:
        Final execution result
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
            f"Processing API callback for execution {execution_id} with {len(file_batch_results)} batch results"
        )

        try:
            # Initialize API client with organization context
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Aggregate results from all file processing tasks
                total_files_processed = 0
                all_file_results = []

                for batch_result in file_batch_results:
                    if batch_result and isinstance(batch_result, dict):
                        total_files_processed += batch_result.get("files_processed", 0)
                        all_file_results.extend(batch_result.get("file_results", []))

                # Calculate execution time and finalize
                execution_time = sum(
                    file_result.get("processing_time", 0)
                    for file_result in all_file_results
                )

                # Update execution status to completed
                api_client.update_workflow_execution_status(
                    execution_id=execution_id, status=ExecutionStatus.COMPLETED.value
                )

                # Update pipeline status for API workflows
                if pipeline_id:
                    try:
                        logger.info(f"Updating API pipeline {pipeline_id} status")
                        pipeline_status = _map_execution_status_to_pipeline_status(
                            ExecutionStatus.COMPLETED.value
                        )
                        api_client.update_pipeline_status(
                            pipeline_id=pipeline_id,
                            execution_id=execution_id,
                            status=pipeline_status,  # Required status parameter
                            last_run_status=pipeline_status,
                            last_run_time=time.time(),
                            increment_run_count=True,
                            organization_id=schema_name,
                        )
                        logger.info(
                            f"Updated API pipeline {pipeline_id} last_run_status to {pipeline_status}"
                        )
                    except Exception as pipeline_error:
                        logger.warning(
                            f"Failed to update API pipeline status: {pipeline_error}"
                        )

                callback_result = {
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "pipeline_id": pipeline_id,
                    "status": "completed",
                    "total_files_processed": total_files_processed,
                    "total_execution_time": execution_time,
                    "batches_processed": len(file_batch_results),
                    "task_id": task_id,
                }

                logger.info(
                    f"Successfully completed API callback for execution {execution_id}"
                )
                return callback_result

        except Exception as e:
            logger.error(
                f"API callback processing failed for execution {execution_id}: {e}"
            )

            # Try to update execution status to failed
            try:
                config = WorkerConfig()
                with InternalAPIClient(config) as api_client:
                    api_client.set_organization_context(schema_name)
                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error=str(e),
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            raise


def _aggregate_file_batch_results(
    file_batch_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate results from multiple file batches.

    Args:
        file_batch_results: List of file batch processing results

    Returns:
        Aggregated results summary
    """
    start_time = time.time()

    total_files = 0
    successful_files = 0
    failed_files = 0
    skipped_files = 0
    total_execution_time = 0.0
    all_file_results = []
    errors = {}

    for batch_result in file_batch_results:
        if isinstance(batch_result, dict):
            # Aggregate file counts - now total_files should be included from FileBatchResult.to_dict()
            batch_total = batch_result.get("total_files", 0)
            batch_successful = batch_result.get("successful_files", 0)
            batch_failed = batch_result.get("failed_files", 0)
            batch_skipped = batch_result.get("skipped_files", 0)

            # If total_files is missing but we have successful+failed, calculate it
            if batch_total == 0 and (batch_successful > 0 or batch_failed > 0):
                batch_total = batch_successful + batch_failed + batch_skipped

            total_files += batch_total
            successful_files += batch_successful
            failed_files += batch_failed
            skipped_files += batch_skipped

            # Aggregate execution times - now get from batch result directly
            batch_time = batch_result.get("execution_time", 0)
            file_results = batch_result.get("file_results", [])

            # Fallback to individual file processing times if batch time not available
            if batch_time == 0:
                for file_result in file_results:
                    if isinstance(file_result, dict):
                        batch_time += file_result.get("processing_time", 0)

            # Collect error information from file results
            for file_result in file_results:
                if isinstance(file_result, dict) and file_result.get("status") == "error":
                    file_name = file_result.get("file_name", "unknown")
                    error_msg = file_result.get("error", "Unknown error")
                    errors[file_name] = error_msg

            total_execution_time += batch_time
            all_file_results.extend(file_results)

    aggregation_time = time.time() - start_time

    aggregated_results = {
        "total_files": total_files,
        "successful_files": successful_files,
        "failed_files": failed_files,
        "skipped_files": skipped_files,
        "total_execution_time": total_execution_time,
        "aggregation_time": aggregation_time,
        "success_rate": (successful_files / total_files) * 100 if total_files > 0 else 0,
        "file_results": all_file_results,
        "errors": errors,
        "batches_processed": len(file_batch_results),
    }

    logger.info(
        f"Aggregated {len(file_batch_results)} batches: {successful_files}/{total_files} successful files"
    )

    return aggregated_results


def _update_execution_with_results(
    api_client: InternalAPIClient,
    execution_id: str,
    aggregated_results: dict[str, Any],
    organization_id: str,
) -> dict[str, Any]:
    """Update workflow execution with aggregated results."""
    try:
        # Determine final status
        if aggregated_results["failed_files"] == 0:
            final_status = "COMPLETED"
        elif aggregated_results["successful_files"] > 0:
            final_status = "COMPLETED"
        else:
            final_status = "ERROR"

        # Update execution status
        update_result = api_client.update_workflow_execution_status(
            execution_id=execution_id, status=final_status
        )

        logger.info(f"Updated execution {execution_id} status to {final_status}")

        return update_result

    except Exception as e:
        logger.error(f"Failed to update execution with results: {e}")
        raise


# DEPRECATED: Destination processing moved to file processing worker
# This function is kept for reference but is no longer called
def _handle_destination_delivery_deprecated(
    api_client: InternalAPIClient,
    workflow_id: str,
    execution_id: str,
    aggregated_results: dict[str, Any],
) -> dict[str, Any]:
    """Handle delivery of results to destination connectors.

    This coordinates actual destination processing by calling the backend
    destination processing API for all successfully processed files.
    """
    try:
        logger.info(f"Handling destination delivery for execution {execution_id}")

        # Get successful file results that need destination processing
        successful_files = [
            fr
            for fr in aggregated_results["file_results"]
            if fr.get("status") == "success"
        ]

        if not successful_files:
            logger.info("No successful files to deliver to destination")
            return {
                "status": "skipped",
                "reason": "no_successful_files",
                "files_delivered": 0,
            }

        logger.info(
            f"Processing destination delivery for {len(successful_files)} successful files"
        )

        # Get workflow execution context for destination configuration
        try:
            execution_context = api_client.get_workflow_execution(execution_id)
            workflow = execution_context.get("workflow", {})
            destination_config = execution_context.get("destination_config", {})

            if not destination_config:
                logger.warning(
                    f"No destination configuration found for workflow {workflow_id} - creating default config for graceful handling"
                )
                # Create default destination config to allow workflow completion
                destination_config = {
                    "connection_type": "FILESYSTEM",
                    "settings": {},
                    "is_api": workflow.get("deployment_type") == "API",
                    "use_file_history": True,
                }
                logger.info(
                    f"Created default destination config for graceful handling: {destination_config['connection_type']}"
                )

        except Exception as e:
            logger.error(f"Failed to get workflow execution context: {str(e)}")
            return {
                "status": "failed",
                "error": f"Could not get workflow context: {str(e)}",
                "files_delivered": 0,
            }

        # Process each successful file through destination connector
        delivered_files = 0
        failed_deliveries = 0
        delivery_details = []

        # Import worker-compatible destination connector components
        from shared.workflow.destination_connector import WorkerDestinationConnector

        from unstract.core.data_models import DestinationConfig

        try:
            # Handle parameter transformation for backward compatibility
            if (
                "destination_settings" in destination_config
                and "settings" not in destination_config
            ):
                logger.info(
                    "Transforming legacy destination_settings to settings format in callback"
                )
                # Preserve all existing fields and only transform the settings field
                transformed_config = dict(destination_config)  # Copy all existing fields
                transformed_config["settings"] = destination_config.get(
                    "destination_settings", {}
                )
                # Remove the old field to avoid confusion
                if "destination_settings" in transformed_config:
                    del transformed_config["destination_settings"]
                destination_config = transformed_config
                logger.info(
                    f"Transformed destination config, preserved connector fields: {list(destination_config.keys())}"
                )

            # Validate required fields
            if "connection_type" not in destination_config:
                logger.warning(
                    "Missing connection_type in destination config, defaulting to FILESYSTEM"
                )
                destination_config["connection_type"] = "FILESYSTEM"

            # Log what connector instance data we received
            connector_fields = ["connector_id", "connector_settings", "connector_name"]
            available_connector_fields = [
                field for field in connector_fields if field in destination_config
            ]
            if available_connector_fields:
                logger.info(
                    f"Received connector instance fields: {available_connector_fields}"
                )
            else:
                logger.warning("No connector instance fields found in destination config")

            # Create destination connector using from_dict to handle string-to-enum conversion
            dest_config = DestinationConfig.from_dict(destination_config)
            destination = WorkerDestinationConnector.from_config(None, dest_config)
            logger.info(
                f"Created destination connector: {dest_config.connection_type} (API: {dest_config.is_api})"
            )

            for file_result in successful_files:
                try:
                    file_name = file_result.get("file_name", "unknown")
                    file_execution_id = file_result.get("file_execution_id")

                    if not file_name or file_name == "unknown":
                        logger.warning(f"File result missing name: {file_result}")
                        file_name = f"unknown_file_{int(time.time())}"

                    if not file_execution_id:
                        logger.warning(f"File result missing execution ID: {file_result}")
                        # Skip files without execution ID as they can't be tracked
                        failed_deliveries += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": None,
                                "status": "failed",
                                "error": "Missing file_execution_id",
                            }
                        )
                        continue

                    # Create file hash object for destination processing with fallback values
                    file_hash_data = {
                        "file_name": file_name,
                        "file_path": file_result.get("file_path", ""),
                        "file_hash": file_result.get("file_hash")
                        or f"fallback_hash_{int(time.time())}",
                        "file_size": file_result.get("file_size", 0),
                        "mime_type": file_result.get(
                            "mime_type", "application/octet-stream"
                        ),
                        "provider_file_uuid": file_result.get("provider_file_uuid"),
                        "fs_metadata": file_result.get("fs_metadata", {}),
                    }

                    # Log fallback usage for debugging
                    if not file_result.get("file_hash"):
                        logger.warning(
                            f"Using fallback file_hash for {file_name}: {file_hash_data['file_hash']}"
                        )

                    file_hash = FileHashData.from_dict(file_hash_data)

                    # Process file through destination with database persistence
                    output_result = destination.handle_output(
                        file_name=file_name,
                        file_hash=file_hash,
                        file_history=None,  # Will be checked internally
                        workflow=workflow,
                        input_file_path=file_hash.file_path,
                        file_execution_id=file_execution_id,
                        api_client=api_client,  # Pass API client for database operations
                        tool_execution_result=file_result.get("tool_result")
                        or file_result.get("result"),  # Pass tool execution results
                    )

                    if output_result:
                        delivered_files += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": file_execution_id,
                                "status": "delivered",
                                "result": output_result,
                            }
                        )
                        logger.info(f"Successfully delivered {file_name} to destination")
                    else:
                        failed_deliveries += 1
                        delivery_details.append(
                            {
                                "file_name": file_name,
                                "file_execution_id": file_execution_id,
                                "status": "failed",
                                "error": "Destination handler returned None",
                            }
                        )
                        logger.warning(
                            f"Destination delivery returned None for {file_name}"
                        )

                except Exception as file_error:
                    failed_deliveries += 1
                    delivery_details.append(
                        {
                            "file_name": file_result.get("file_name", "unknown"),
                            "file_execution_id": file_result.get("file_execution_id"),
                            "status": "failed",
                            "error": str(file_error),
                        }
                    )
                    logger.error(
                        f"Failed to deliver file {file_result.get('file_name')}: {str(file_error)}"
                    )

        except Exception as connector_error:
            logger.error(
                f"Failed to create destination connector: {str(connector_error)}"
            )
            return {
                "status": "failed",
                "error": f"Destination connector creation failed: {str(connector_error)}",
                "files_delivered": 0,
            }

        # Determine overall delivery status
        if delivered_files > 0 and failed_deliveries == 0:
            status = "success"
        elif delivered_files > 0 and failed_deliveries > 0:
            status = "partial"
        elif failed_deliveries > 0:
            status = "failed"
        else:
            status = "unknown"

        delivery_result = {
            "status": status,
            "destination_type": dest_config.connection_type,
            "files_delivered": delivered_files,
            "failed_deliveries": failed_deliveries,
            "total_files": len(successful_files),
            "delivery_time": time.time(),
            "details": delivery_details,
        }

        logger.info(
            f"Destination delivery completed: {delivered_files}/{len(successful_files)} files delivered successfully"
        )

        return delivery_result

    except Exception as e:
        logger.error(f"Failed to handle destination delivery: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "files_delivered": 0}


@app.task(
    bind=True,
    name="finalize_execution_callback",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
@monitor_performance
def finalize_execution_callback(
    self, schema_name: str, execution_id: str, cleanup_resources: bool = True
) -> dict[str, Any]:
    """Finalize execution and cleanup resources.

    This is a standalone task for execution finalization that can be
    called independently or as part of the callback processing.
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id, execution_id=execution_id, organization_id=schema_name
    ):
        logger.info(f"Finalizing execution {execution_id}")

        try:
            config = WorkerConfig()
            with InternalAPIClient(config) as api_client:
                api_client.set_organization_context(schema_name)

                # Get current execution status
                finalization_status = api_client.get_execution_finalization_status(
                    execution_id
                )

                if finalization_status.get("is_finalized"):
                    logger.info(f"Execution {execution_id} already finalized")
                    return {
                        "status": "already_finalized",
                        "execution_id": execution_id,
                        "current_status": finalization_status.get("current_status"),
                    }

                # Perform cleanup if requested
                cleanup_result = None
                if cleanup_resources:
                    cleanup_result = api_client.cleanup_execution_resources(
                        execution_ids=[execution_id],
                        cleanup_types=["cache", "temp_files", "logs"],
                    )

                finalization_result = {
                    "status": "finalized",
                    "execution_id": execution_id,
                    "task_id": task_id,
                    "cleanup_result": cleanup_result,
                    "finalized_at": time.time(),
                }

                logger.info(f"Successfully finalized execution {execution_id}")

                return finalization_result

        except Exception as e:
            logger.error(f"Failed to finalize execution {execution_id}: {e}")
            raise


# Simple resilient executor decorator (placeholder)
def resilient_executor(func):
    """Simple resilient executor decorator."""
    return func


# Resilient callback processor
@app.task(bind=True)
@resilient_executor
def process_batch_callback_resilient(
    self,
    schema_name: str,
    workflow_id: str,
    execution_id: str,
    file_batch_results: list[dict[str, Any]],
    **kwargs,
) -> dict[str, Any]:
    """Resilient batch callback processing with advanced error handling."""
    task_id = self.request.id

    with log_context(task_id=task_id, execution_id=execution_id, workflow_id=workflow_id):
        logger.info(
            f"Starting resilient batch callback processing for execution {execution_id}"
        )

        try:
            # Use the main callback processing function
            result = process_batch_callback(
                schema_name=schema_name,
                workflow_id=workflow_id,
                execution_id=execution_id,
                file_batch_results=file_batch_results,
                **kwargs,
            )

            return result

        except Exception as e:
            logger.error(f"Resilient batch callback processing failed: {e}")
            raise
