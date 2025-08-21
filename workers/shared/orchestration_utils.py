"""Workflow Orchestration Utilities for Worker Tasks

This module provides standardized workflow orchestration patterns,
chord execution, batch processing, and task coordination utilities.
"""

import os
from typing import Any

from celery import chord

from .enums import FileDestinationType, PipelineType
from .enums.task_enums import QueueName
from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkflowOrchestrationUtils:
    """Centralized workflow orchestration patterns and utilities."""

    @staticmethod
    def create_chord_execution(
        batch_tasks: list[Any],
        callback_task_name: str,
        callback_kwargs: dict[str, Any],
        callback_queue: str,
        app_instance: Any,
    ) -> Any:
        """Standardized chord creation and execution pattern.

        Args:
            batch_tasks: List of batch task signatures
            callback_task_name: Name of callback task
            callback_kwargs: Keyword arguments for callback
            callback_queue: Queue name for callback task
            app_instance: Celery app instance

        Returns:
            Chord result object

        Note:
            This consolidates the identical chord creation pattern found in
            api-deployment and general workers.
        """
        try:
            callback_signature = app_instance.signature(
                callback_task_name,
                kwargs=callback_kwargs,
                queue=callback_queue,
            )

            result = chord(batch_tasks)(callback_signature)

            logger.info(
                f"Chord execution started - "
                f"batch_tasks={len(batch_tasks)}, "
                f"callback={callback_task_name}, "
                f"queue={callback_queue}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to create chord execution: {e}")
            raise

    @staticmethod
    def determine_manual_review_routing(
        files: dict[str, Any],
        manual_review_config: dict[str, Any] | None = None,
        default_destination: str = FileDestinationType.DESTINATION.value,
    ) -> dict[str, str]:
        """Determine manual review routing for files based on configuration.

        Args:
            files: Dictionary of files to route
            manual_review_config: Manual review configuration
            default_destination: Default destination if no manual review

        Returns:
            Dictionary mapping file keys to destinations

        Note:
            This consolidates the complex manual review decision logic found
            across multiple workers.
        """
        routing = {}
        manual_review_required = False

        # Check if manual review is globally enabled
        if manual_review_config:
            manual_review_required = manual_review_config.get("enabled", False)

        for file_key, file_data in files.items():
            if manual_review_required:
                # Additional per-file checks could go here
                routing[file_key] = FileDestinationType.MANUALREVIEW.value
                logger.debug(f"File {file_key} routed to manual review")
            else:
                routing[file_key] = default_destination
                logger.debug(f"File {file_key} routed to {default_destination}")

        if manual_review_required:
            logger.info(f"Manual review routing: {len(files)} files routed for review")

        return routing

    @staticmethod
    def create_batch_task_signatures(
        batch_files: list[Any],
        task_name: str,
        base_kwargs: dict[str, Any],
        queue_name: str,
        app_instance: Any,
    ) -> list[Any]:
        """Create standardized batch task signatures.

        Args:
            batch_files: List of file batches
            task_name: Name of task to execute
            base_kwargs: Base keyword arguments for all tasks
            queue_name: Queue name for task execution
            app_instance: Celery app instance

        Returns:
            List of task signatures

        Note:
            This standardizes batch task signature creation across workers.
        """
        signatures = []

        for batch_index, batch in enumerate(batch_files):
            batch_kwargs = base_kwargs.copy()
            batch_kwargs.update(
                {
                    "batch_files": batch,
                    "batch_index": batch_index,
                    "total_batches": len(batch_files),
                }
            )

            signature = app_instance.signature(
                task_name, kwargs=batch_kwargs, queue=queue_name
            )
            signatures.append(signature)

        logger.info(
            f"Created {len(signatures)} batch task signatures for {task_name} "
            f"on queue {queue_name}"
        )

        return signatures

    @staticmethod
    def calculate_batch_processing_metrics(
        total_files: int, batch_size: int, processing_time_seconds: float | None = None
    ) -> dict[str, int | float]:
        """Calculate batch processing metrics for monitoring and optimization.

        Args:
            total_files: Total number of files processed
            batch_size: Size of each batch
            processing_time_seconds: Total processing time

        Returns:
            Dictionary of metrics

        Note:
            This provides consistent metrics calculation across orchestration.
        """
        num_batches = (total_files + batch_size - 1) // batch_size  # Ceiling division
        avg_files_per_batch = total_files / num_batches if num_batches > 0 else 0

        metrics = {
            "total_files": total_files,
            "batch_size": batch_size,
            "num_batches": num_batches,
            "avg_files_per_batch": avg_files_per_batch,
        }

        if processing_time_seconds is not None:
            metrics.update(
                {
                    "processing_time_seconds": processing_time_seconds,
                    "avg_time_per_batch": processing_time_seconds / num_batches
                    if num_batches > 0
                    else 0,
                    "avg_time_per_file": processing_time_seconds / total_files
                    if total_files > 0
                    else 0,
                }
            )

        return metrics

    @staticmethod
    def determine_callback_queue(
        workflow_type: str, default_queue: str = "celery"
    ) -> str:
        """Determine appropriate callback queue based on workflow type.

        Args:
            workflow_type: Type of workflow being processed
            default_queue: Default queue if no specific mapping

        Returns:
            Queue name for callback processing

        Note:
            This centralizes queue determination logic found across workers.
        """
        # Map workflow types to specific queues using enums
        queue_mapping = {
            PipelineType.API.value: QueueName.CELERY_API_DEPLOYMENTS.value,
            PipelineType.ETL.value: QueueName.CELERY.value,
            PipelineType.TASK.value: QueueName.CELERY.value,
            PipelineType.APP.value: QueueName.CELERY.value,
        }

        # Check for environment-specific overrides
        env_queue = os.getenv(f"CALLBACK_QUEUE_{workflow_type}")
        if env_queue:
            logger.info(
                f"Using environment-specified queue for {workflow_type}: {env_queue}"
            )
            return env_queue

        queue = queue_mapping.get(workflow_type.upper(), default_queue)
        logger.debug(f"Determined callback queue for {workflow_type}: {queue}")

        return queue

    @staticmethod
    def create_callback_signature_data(
        execution_id: str,
        workflow_id: str,
        organization_id: str,
        additional_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create standardized callback signature data.

        Args:
            execution_id: Workflow execution ID
            workflow_id: Workflow ID
            organization_id: Organization ID
            additional_context: Additional context data

        Returns:
            Dictionary of callback signature data

        Note:
            This standardizes callback signature creation across workers.
        """
        callback_data = {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "organization_id": organization_id,
            "callback_metadata": {
                "created_at": None,  # Will be set by callback handler
                "orchestrator": "WorkflowOrchestrationUtils",
            },
        }

        if additional_context:
            callback_data.update(additional_context)

        return callback_data

    @staticmethod
    def validate_orchestration_parameters(
        execution_id: str,
        workflow_id: str,
        organization_id: str,
        files: dict[str, Any] | None = None,
    ) -> None:
        """Validate common orchestration parameters.

        Args:
            execution_id: Workflow execution ID
            workflow_id: Workflow ID
            organization_id: Organization ID
            files: Optional files dictionary

        Raises:
            ValueError: If validation fails

        Note:
            This provides consistent parameter validation across orchestration.
        """
        if not execution_id:
            raise ValueError("execution_id is required for workflow orchestration")

        if not workflow_id:
            raise ValueError("workflow_id is required for workflow orchestration")

        if not organization_id:
            raise ValueError("organization_id is required for workflow orchestration")

        if files is not None and not isinstance(files, dict):
            raise ValueError("files must be a dictionary when provided")

        logger.debug(
            f"Orchestration parameters validated - "
            f"exec_id={execution_id}, workflow_id={workflow_id}, org_id={organization_id}"
        )


class WorkflowOrchestrationMixin:
    """Mixin class to add orchestration utilities to worker tasks."""

    def create_chord(
        self, batch_tasks, callback_task_name, callback_kwargs, callback_queue
    ):
        """Create chord using standardized pattern."""
        # Get app instance from task context
        app_instance = getattr(self, "app", None)
        if not app_instance:
            raise RuntimeError("Celery app instance not available in task context")

        return WorkflowOrchestrationUtils.create_chord_execution(
            batch_tasks, callback_task_name, callback_kwargs, callback_queue, app_instance
        )

    def determine_manual_review_routing(self, files, manual_review_config=None):
        """Determine manual review routing using standardized logic."""
        return WorkflowOrchestrationUtils.determine_manual_review_routing(
            files, manual_review_config
        )

    def create_batch_signatures(self, batch_files, task_name, base_kwargs, queue_name):
        """Create batch task signatures using standardized pattern."""
        app_instance = getattr(self, "app", None)
        if not app_instance:
            raise RuntimeError("Celery app instance not available in task context")

        return WorkflowOrchestrationUtils.create_batch_task_signatures(
            batch_files, task_name, base_kwargs, queue_name, app_instance
        )

    def calculate_metrics(self, total_files, batch_size, processing_time=None):
        """Calculate processing metrics using standardized calculation."""
        return WorkflowOrchestrationUtils.calculate_batch_processing_metrics(
            total_files, batch_size, processing_time
        )

    def determine_callback_queue(self, workflow_type, default_queue="celery"):
        """Determine callback queue using standardized logic."""
        return WorkflowOrchestrationUtils.determine_callback_queue(
            workflow_type, default_queue
        )

    def create_callback_data(self, execution_id, workflow_id, organization_id, **kwargs):
        """Create callback signature data using standardized format."""
        return WorkflowOrchestrationUtils.create_callback_signature_data(
            execution_id, workflow_id, organization_id, kwargs
        )

    def validate_parameters(self, execution_id, workflow_id, organization_id, files=None):
        """Validate orchestration parameters using standardized validation."""
        WorkflowOrchestrationUtils.validate_orchestration_parameters(
            execution_id, workflow_id, organization_id, files
        )
