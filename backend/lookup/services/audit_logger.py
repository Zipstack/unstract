"""Audit Logger implementation for tracking Look-Up executions.

This module provides functionality to log all Look-Up execution details
to the database for debugging, monitoring, and compliance purposes.
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from lookup.models import LookupExecutionAudit, LookupProject

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs Look-Up execution details to lookup_execution_audit table.

    This class provides methods to record all aspects of Look-Up executions
    including inputs, outputs, performance metrics, and errors for audit
    trail and debugging purposes.
    """

    def log_execution(
        self,
        execution_id: str,
        lookup_project_id: UUID,
        prompt_studio_project_id: UUID | None,
        input_data: dict[str, Any],
        reference_data_version: int,
        llm_provider: str,
        llm_model: str,
        llm_prompt: str,
        llm_response: str | None,
        enriched_output: dict[str, Any] | None,
        status: str,  # 'success', 'partial', 'failed'
        confidence_score: float | None = None,
        execution_time_ms: int | None = None,
        llm_call_time_ms: int | None = None,
        llm_response_cached: bool = False,
        error_message: str | None = None,
        file_execution_id: UUID | None = None,
    ) -> LookupExecutionAudit | None:
        """Log execution to database.

        Records comprehensive details about a Look-Up execution including
        the input data, LLM interaction, output, and performance metrics.

        Args:
            execution_id: UUID of the orchestration execution
            lookup_project_id: UUID of the Look-Up project
            prompt_studio_project_id: Optional UUID of PS project
            input_data: Input data used for variable resolution
            reference_data_version: Version of reference data used
            llm_provider: LLM provider name (e.g., 'openai')
            llm_model: LLM model name (e.g., 'gpt-4')
            llm_prompt: Final resolved prompt sent to LLM
            llm_response: Raw response from LLM
            enriched_output: Parsed enrichment data
            status: Execution status ('success', 'partial', 'failed')
            confidence_score: Optional confidence score (0.0-1.0)
            execution_time_ms: Total execution time in milliseconds
            llm_call_time_ms: Time spent calling LLM in milliseconds
            llm_response_cached: Whether response was from cache
            error_message: Error message if execution failed
            file_execution_id: Optional workflow file execution ID for tracking

        Returns:
            Created LookupExecutionAudit instance or None if logging fails

        Example:
            >>> logger = AuditLogger()
            >>> audit = logger.log_execution(
            ...     execution_id='abc-123',
            ...     lookup_project_id=project_id,
            ...     status='success',
            ...     ...
            ... )
        """
        try:
            # Get the Look-Up project
            try:
                lookup_project = LookupProject.objects.get(id=lookup_project_id)
            except LookupProject.DoesNotExist:
                logger.error(f"Look-Up project {lookup_project_id} not found for audit")
                return None

            # Convert confidence score to Decimal if provided
            if confidence_score is not None:
                confidence_score = Decimal(str(confidence_score))

            # Create audit record
            audit = LookupExecutionAudit.objects.create(
                lookup_project=lookup_project,
                prompt_studio_project_id=prompt_studio_project_id,
                execution_id=execution_id,
                file_execution_id=file_execution_id,
                input_data=input_data,
                reference_data_version=reference_data_version,
                enriched_output=enriched_output,
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_prompt=llm_prompt,
                llm_response=llm_response,
                llm_response_cached=llm_response_cached,
                execution_time_ms=execution_time_ms,
                llm_call_time_ms=llm_call_time_ms,
                status=status,
                error_message=error_message,
                confidence_score=confidence_score,
            )

            logger.debug(
                f"Logged execution audit {audit.id} for Look-Up {lookup_project.name} "
                f"(execution {execution_id})"
            )

            return audit

        except Exception as e:
            # Log error but don't fail the execution
            logger.exception(
                f"Failed to log execution audit for {lookup_project_id}: {str(e)}"
            )
            return None

    def log_success(
        self, execution_id: str, project_id: UUID, **kwargs
    ) -> LookupExecutionAudit | None:
        """Convenience method for logging successful execution.

        Args:
            execution_id: UUID of the orchestration execution
            project_id: UUID of the Look-Up project
            **kwargs: Additional parameters to pass to log_execution

        Returns:
            Created audit record or None if logging fails

        Example:
            >>> audit = logger.log_success(
            ...     execution_id="abc-123",
            ...     project_id=project_id,
            ...     input_data={"vendor": "Slack"},
            ...     enriched_output={"canonical_vendor": "Slack"},
            ...     confidence_score=0.92,
            ... )
        """
        return self.log_execution(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status="success",
            **kwargs,
        )

    def log_failure(
        self, execution_id: str, project_id: UUID, error: str, **kwargs
    ) -> LookupExecutionAudit | None:
        """Convenience method for logging failed execution.

        Args:
            execution_id: UUID of the orchestration execution
            project_id: UUID of the Look-Up project
            error: Error message describing the failure
            **kwargs: Additional parameters to pass to log_execution

        Returns:
            Created audit record or None if logging fails

        Example:
            >>> audit = logger.log_failure(
            ...     execution_id="abc-123",
            ...     project_id=project_id,
            ...     error="LLM timeout after 30 seconds",
            ...     input_data={"vendor": "Slack"},
            ... )
        """
        return self.log_execution(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status="failed",
            error_message=error,
            **kwargs,
        )

    def log_partial(
        self, execution_id: str, project_id: UUID, **kwargs
    ) -> LookupExecutionAudit | None:
        """Convenience method for logging partial success.

        Used when some enrichment was achieved but with issues
        (e.g., low confidence, incomplete data).

        Args:
            execution_id: UUID of the orchestration execution
            project_id: UUID of the Look-Up project
            **kwargs: Additional parameters to pass to log_execution

        Returns:
            Created audit record or None if logging fails

        Example:
            >>> audit = logger.log_partial(
            ...     execution_id="abc-123",
            ...     project_id=project_id,
            ...     input_data={"vendor": "Unknown Corp"},
            ...     enriched_output={"canonical_vendor": "Unknown"},
            ...     confidence_score=0.35,
            ...     error_message="Low confidence match",
            ... )
        """
        return self.log_execution(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status="partial",
            **kwargs,
        )

    def get_execution_history(self, execution_id: str, limit: int = 100) -> list:
        """Retrieve audit records for a specific execution.

        Args:
            execution_id: UUID of the orchestration execution
            limit: Maximum number of records to return

        Returns:
            List of LookupExecutionAudit instances

        Example:
            >>> history = logger.get_execution_history("abc-123")
            >>> for audit in history:
            ...     print(f"{audit.lookup_project.name}: {audit.status}")
        """
        try:
            return list(
                LookupExecutionAudit.objects.filter(execution_id=execution_id)
                .select_related("lookup_project")
                .order_by("executed_at")[:limit]
            )
        except Exception as e:
            logger.error(f"Failed to retrieve execution history: {str(e)}")
            return []

    def get_project_stats(self, project_id: UUID, limit: int = 1000) -> dict[str, Any]:
        """Get execution statistics for a Look-Up project.

        Args:
            project_id: UUID of the Look-Up project
            limit: Maximum number of records to analyze

        Returns:
            Dictionary with statistics including success rate,
            average execution time, cache hit rate, etc.

        Example:
            >>> stats = logger.get_project_stats(project_id)
            >>> print(f"Success rate: {stats['success_rate']:.1%}")
        """
        try:
            audits = LookupExecutionAudit.objects.filter(
                lookup_project_id=project_id
            ).order_by("-executed_at")[:limit]

            total = len(audits)
            if total == 0:
                return {
                    "total_executions": 0,
                    "success_rate": 0.0,
                    "avg_execution_time_ms": 0,
                    "cache_hit_rate": 0.0,
                    "avg_confidence": 0.0,
                }

            successful = sum(1 for a in audits if a.status == "success")
            cached = sum(1 for a in audits if a.llm_response_cached)

            exec_times = [
                a.execution_time_ms for a in audits if a.execution_time_ms is not None
            ]
            avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 0

            confidence_scores = [
                float(a.confidence_score)
                for a in audits
                if a.confidence_score is not None
            ]
            avg_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores
                else 0.0
            )

            return {
                "total_executions": total,
                "success_rate": successful / total if total > 0 else 0.0,
                "avg_execution_time_ms": int(avg_exec_time),
                "cache_hit_rate": cached / total if total > 0 else 0.0,
                "avg_confidence": avg_confidence,
                "successful": successful,
                "failed": sum(1 for a in audits if a.status == "failed"),
                "partial": sum(1 for a in audits if a.status == "partial"),
            }

        except Exception as e:
            logger.error(f"Failed to get project stats: {str(e)}")
            return {
                "total_executions": 0,
                "success_rate": 0.0,
                "avg_execution_time_ms": 0,
                "cache_hit_rate": 0.0,
                "avg_confidence": 0.0,
            }
