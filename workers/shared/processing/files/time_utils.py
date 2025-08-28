"""Time calculation utilities for workflow execution timing."""

import time
from datetime import datetime
from typing import Any

import pytz
from shared.api import InternalAPIClient
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WallClockTimeCalculator:
    """Utility class to calculate wall-clock execution time with fallback strategies."""

    @staticmethod
    def calculate_execution_time(
        api_client: InternalAPIClient,
        execution_id: str,
        organization_id: str,
        fallback_results: list[dict[str, Any]] = None,
    ) -> float:
        """Calculate wall-clock execution time with multiple fallback strategies.

        Args:
            api_client: API client instance
            execution_id: Workflow execution ID
            organization_id: Organization context
            fallback_results: List of file results for summing as fallback

        Returns:
            Execution time in seconds
        """
        try:
            # Primary: Get workflow execution start time from backend
            return WallClockTimeCalculator._get_wall_clock_time(
                api_client, execution_id, organization_id
            )
        except Exception as e:
            logger.error(f"Error calculating wall-clock time: {e}")
            # Fallback: Sum individual file processing times
            return WallClockTimeCalculator._get_fallback_time(fallback_results or [])

    @staticmethod
    def _get_wall_clock_time(
        api_client: InternalAPIClient, execution_id: str, organization_id: str
    ) -> float:
        """Get wall-clock time from execution created_at timestamp."""
        execution_response = api_client.get_workflow_execution(
            execution_id, organization_id
        )

        if not (execution_response.success and execution_response.data):
            raise ValueError("Failed to get execution data from API")

        # DEBUG: Log the full API response to understand the issue
        logger.info(
            f"DEBUG: API response keys: {list(execution_response.data.keys()) if execution_response.data else 'None'}"
        )

        # Extract execution data from the nested structure
        execution_data = execution_response.data.get("execution", {})
        if not execution_data:
            logger.error(
                f"No 'execution' key in API response. Available keys: {list(execution_response.data.keys())}"
            )
            raise ValueError("No execution data found in API response")

        # Get created_at from the execution data
        created_at_str = execution_data.get("created_at")

        logger.info(
            f"DEBUG: Execution data keys: {list(execution_data.keys()) if execution_data else 'None'}"
        )
        logger.info(f"DEBUG: created_at value: {created_at_str}")

        if not created_at_str:
            logger.error(
                f"Missing timestamp field in API response. Available fields: {list(execution_response.data.keys())}"
            )
            # Don't raise error, let it fall back to file timing calculation
            raise ValueError("No created_at timestamp found in execution data")

        # Parse Django timestamp format
        created_at = WallClockTimeCalculator._parse_django_timestamp(created_at_str)

        # Calculate wall-clock execution time
        now = datetime.now(pytz.UTC)
        wall_clock_time = (now - created_at).total_seconds()

        logger.info(f"✅ Wall-clock execution time: {wall_clock_time:.2f}s")
        return wall_clock_time

    @staticmethod
    def _parse_django_timestamp(timestamp_str: str) -> datetime:
        """Parse Django timestamp format with timezone handling."""
        if timestamp_str.endswith("Z"):
            # UTC format: "2024-01-01T12:00:00.123456Z"
            return datetime.fromisoformat(timestamp_str[:-1]).replace(tzinfo=pytz.UTC)
        else:
            # Local format: "2024-01-01T12:00:00.123456"
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt

    @staticmethod
    def _get_fallback_time(file_results: list[dict[str, Any]]) -> float:
        """Calculate fallback time by summing individual file processing times."""
        if not file_results:
            logger.warning(
                "⚠️ No file results available for timing calculation, using default 30s"
            )
            return 30.0  # Reasonable default for pipeline execution

        # Try different possible field names for processing time
        fallback_time = 0.0
        for file_result in file_results:
            processing_time = (
                file_result.get("processing_time", 0)
                or file_result.get("execution_time", 0)
                or file_result.get("duration", 0)
                or file_result.get("time_taken", 0)
            )
            fallback_time += processing_time

        if fallback_time == 0.0:
            # If still no timing data, use reasonable estimate based on file count
            estimated_time = len(file_results) * 15.0  # ~15s per file estimate
            logger.warning(
                f"⚠️ No timing data in file results, estimating {estimated_time:.2f}s for {len(file_results)} files"
            )
            return estimated_time

        logger.warning(f"⚠️ Using fallback sum of file times: {fallback_time:.2f}s")
        return fallback_time


def aggregate_file_batch_results(
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
