"""Look-Up Orchestrator implementation for parallel execution.

This module provides functionality to execute multiple Look-Up projects
in parallel and merge their results into a single enriched output.
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import UTC, datetime
from typing import Any

from lookup.models import LookupProject
from lookup.services.enrichment_merger import EnrichmentMerger
from lookup.services.lookup_executor import LookUpExecutor

logger = logging.getLogger(__name__)


class LookUpOrchestrator:
    """Orchestrates parallel execution of multiple Look-Up projects.

    This class manages the concurrent execution of multiple Look-Up projects,
    handles timeouts, collects results, and merges them into a single
    enriched output using the EnrichmentMerger.
    """

    def __init__(
        self,
        executor: LookUpExecutor,
        merger: EnrichmentMerger,
        config: dict[str, Any] = None,
    ):
        """Initialize the Look-Up orchestrator.

        Args:
            executor: LookUpExecutor instance for single Look-Up execution
            merger: EnrichmentMerger instance for combining results
            config: Configuration dictionary with optional keys:
                - max_concurrent_executions: Maximum parallel executions (default 10)
                - queue_timeout_seconds: Overall queue timeout (default 120)
                - execution_timeout_seconds: Per-execution timeout (default 30)
        """
        self.executor = executor
        self.merger = merger

        config = config or {}
        self.max_concurrent = config.get("max_concurrent_executions", 10)
        self.queue_timeout = config.get("queue_timeout_seconds", 120)
        self.execution_timeout = config.get("execution_timeout_seconds", 30)

        logger.info(
            f"Orchestrator initialized with max_concurrent={self.max_concurrent}, "
            f"queue_timeout={self.queue_timeout}s, "
            f"execution_timeout={self.execution_timeout}s"
        )

    def execute_lookups(
        self,
        input_data: dict[str, Any],
        lookup_projects: list[LookupProject],
        execution_id: str | None = None,
        prompt_studio_project_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute all Look-Ups in parallel and merge results.

        Submits all Look-Up projects for parallel execution, collects
        the results, and merges successful enrichments into a single
        output. Handles timeouts and failures gracefully.

        Args:
            input_data: Input data to enrich
            lookup_projects: List of Look-Up projects to execute
            execution_id: Optional UUID to group related executions for audit
            prompt_studio_project_id: Optional PS project ID for audit tracking

        Returns:
            Dictionary containing:
                - lookup_enrichment: Merged enrichment data
                - _lookup_metadata: Execution metadata including:
                    - execution_id: Unique ID for this execution
                    - executed_at: ISO8601 timestamp
                    - total_execution_time_ms: Total time in milliseconds
                    - lookups_executed: Number of Look-Ups attempted
                    - lookups_successful: Number of successful executions
                    - lookups_failed: Number of failed executions
                    - conflicts_resolved: Number of field conflicts resolved
                    - enrichments: List of individual enrichment results

        Example:
            >>> orchestrator = LookUpOrchestrator(executor, merger)
            >>> projects = [vendor_lookup, product_lookup]
            >>> result = orchestrator.execute_lookups({"vendor": "Slack"}, projects)
            >>> print(result["lookup_enrichment"])
            {'canonical_vendor': 'Slack', 'product_type': 'SaaS'}
            >>> print(result["_lookup_metadata"]["lookups_successful"])
            2
        """
        execution_id = execution_id or str(uuid.uuid4())
        start_time = time.time()
        executed_at = datetime.now(UTC).isoformat()

        logger.info(
            f"Starting orchestrated execution {execution_id} for "
            f"{len(lookup_projects)} Look-Up projects"
        )

        if not lookup_projects:
            # No Look-Ups to execute
            return self._empty_result(execution_id, executed_at, start_time)

        successful_enrichments = []
        failed_lookups = []
        timeout_count = 0

        # Build project order mapping for sorting results later
        project_order = {
            str(project.id): idx for idx, project in enumerate(lookup_projects)
        }

        # Execute Look-Ups in parallel
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as thread_executor:
            # Submit all tasks
            futures = {
                thread_executor.submit(
                    self._execute_single,
                    execution_id,
                    input_data,
                    lookup_project,
                    prompt_studio_project_id,
                ): lookup_project
                for lookup_project in lookup_projects
            }

            logger.debug(f"Submitted {len(futures)} Look-Up tasks for parallel execution")

            # Collect results with timeout
            try:
                for future in as_completed(futures, timeout=self.queue_timeout):
                    lookup_project = futures[future]
                    try:
                        result = future.result(timeout=self.execution_timeout)

                        if result["status"] == "success":
                            successful_enrichments.append(result)
                            logger.debug(
                                f"Look-Up {lookup_project.name} completed successfully"
                            )
                        else:
                            failed_lookups.append(result)
                            logger.warning(
                                f"Look-Up {lookup_project.name} failed: {result.get('error')}"
                            )

                    except TimeoutError:
                        # Individual execution timeout
                        timeout_count += 1
                        logger.error(
                            f"Look-Up {lookup_project.name} timed out after "
                            f"{self.execution_timeout}s"
                        )
                        failed_lookups.append(
                            {
                                "status": "failed",
                                "project_id": str(lookup_project.id),
                                "project_name": lookup_project.name,
                                "error": f"Execution timeout ({self.execution_timeout}s)",
                                "execution_time_ms": self.execution_timeout * 1000,
                                "cached": False,
                            }
                        )

                    except Exception as e:
                        # Unexpected error in future.result()
                        logger.exception(
                            f"Unexpected error getting result for {lookup_project.name}"
                        )
                        failed_lookups.append(
                            {
                                "status": "failed",
                                "project_id": str(lookup_project.id),
                                "project_name": lookup_project.name,
                                "error": f"Execution error: {str(e)}",
                                "execution_time_ms": 0,
                                "cached": False,
                            }
                        )

            except TimeoutError:
                # Overall queue timeout
                logger.error(
                    f"Queue timeout after {self.queue_timeout}s, "
                    f"some Look-Ups may not have completed"
                )
                # Cancel remaining futures
                for future in futures:
                    if not future.done():
                        future.cancel()
                        lookup_project = futures[future]
                        failed_lookups.append(
                            {
                                "status": "failed",
                                "project_id": str(lookup_project.id),
                                "project_name": lookup_project.name,
                                "error": f"Queue timeout ({self.queue_timeout}s)",
                                "execution_time_ms": 0,
                                "cached": False,
                            }
                        )

        # Sort successful enrichments by original execution order before merging
        # This ensures that when there's no confidence score, the lookup with
        # lower execution_order (higher priority) wins in conflict resolution
        if successful_enrichments:
            successful_enrichments.sort(
                key=lambda x: project_order.get(x.get("project_id"), 999)
            )
            merge_result = self.merger.merge(successful_enrichments)
            merged_data = merge_result["data"]
            conflicts_resolved = merge_result["conflicts_resolved"]
            # enrichment_details = merge_result["enrichment_details"]
        else:
            # No successful enrichments
            merged_data = {}
            conflicts_resolved = 0

        # Calculate execution time
        total_execution_time_ms = int((time.time() - start_time) * 1000)

        # Combine all enrichment results (successful and failed)
        all_enrichments = successful_enrichments + failed_lookups

        logger.info(
            f"Orchestration {execution_id} completed: "
            f"{len(successful_enrichments)} successful, "
            f"{len(failed_lookups)} failed, "
            f"{timeout_count} timeouts, "
            f"{conflicts_resolved} conflicts resolved, "
            f"total time {total_execution_time_ms}ms"
        )
        logger.info(f"Merged enrichment data: {merged_data}")

        return {
            "lookup_enrichment": merged_data,
            "_lookup_metadata": {
                "execution_id": execution_id,
                "executed_at": executed_at,
                "total_execution_time_ms": total_execution_time_ms,
                "lookups_executed": len(lookup_projects),
                "lookups_successful": len(successful_enrichments),
                "lookups_failed": len(failed_lookups),
                "conflicts_resolved": conflicts_resolved,
                "enrichments": all_enrichments,
            },
        }

    def _execute_single(
        self,
        execution_id: str,
        input_data: dict[str, Any],
        lookup_project: LookupProject,
        prompt_studio_project_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single Look-Up project.

        Wrapper around the executor to add execution context and
        handle any unexpected errors.

        Args:
            execution_id: ID of the orchestration execution
            input_data: Input data for enrichment
            lookup_project: Look-Up project to execute
            prompt_studio_project_id: Optional PS project ID for audit tracking

        Returns:
            Enrichment result dictionary from the executor
        """
        try:
            logger.debug(
                f"Executing Look-Up {lookup_project.name} for execution {execution_id}"
            )

            # Execute the Look-Up with audit context
            result = self.executor.execute(
                lookup_project=lookup_project,
                input_data=input_data,
                execution_id=execution_id,
                prompt_studio_project_id=prompt_studio_project_id,
            )

            # Add execution context
            result["execution_id"] = execution_id

            # Filter enrichment data to only include fields that actually changed
            # This prevents a lookup from overwriting fields it didn't canonicalize
            if result.get("status") == "success" and result.get("data"):
                result["data"] = self._filter_changed_fields(input_data, result["data"])
                logger.debug(
                    f"Filtered enrichment for {lookup_project.name}: "
                    f"{list(result['data'].keys())}"
                )

            return result

        except Exception as e:
            # Catch any unexpected errors from the executor
            logger.exception(f"Unexpected error executing Look-Up {lookup_project.name}")
            return {
                "status": "failed",
                "project_id": str(lookup_project.id),
                "project_name": lookup_project.name,
                "error": f"Unexpected error: {str(e)}",
                "execution_time_ms": 0,
                "cached": False,
                "execution_id": execution_id,
            }

    def _filter_changed_fields(
        self,
        input_data: dict[str, Any],
        enrichment_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Filter enrichment data to only include fields that changed.

        When an LLM returns the entire input with modifications, this method
        identifies which fields actually changed and returns only those.
        This prevents one lookup from overwriting fields that another lookup
        is responsible for canonicalizing.

        Args:
            input_data: Original input data before enrichment
            enrichment_data: Data returned by the lookup

        Returns:
            Dictionary containing only fields that differ from input_data,
            plus any new fields not present in input_data
        """
        changed_fields = {}

        for field_name, enriched_value in enrichment_data.items():
            # Include field if:
            # 1. It's a new field not in input_data, OR
            # 2. The value is different from the input value
            if field_name not in input_data:
                # New field added by the lookup
                changed_fields[field_name] = enriched_value
            elif input_data[field_name] != enriched_value:
                # Field value was changed by the lookup
                changed_fields[field_name] = enriched_value
            # else: field unchanged, don't include it

        return changed_fields

    def _empty_result(
        self, execution_id: str, executed_at: str, start_time: float
    ) -> dict[str, Any]:
        """Build result for empty Look-Up list.

        Args:
            execution_id: Execution ID
            executed_at: Execution timestamp
            start_time: Start time for calculating duration

        Returns:
            Empty result dictionary with metadata
        """
        total_execution_time_ms = int((time.time() - start_time) * 1000)

        return {
            "lookup_enrichment": {},
            "_lookup_metadata": {
                "execution_id": execution_id,
                "executed_at": executed_at,
                "total_execution_time_ms": total_execution_time_ms,
                "lookups_executed": 0,
                "lookups_successful": 0,
                "lookups_failed": 0,
                "conflicts_resolved": 0,
                "enrichments": [],
            },
        }
