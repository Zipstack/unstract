"""Redis-backed state management for multi-stage pipeline processing."""

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from django.core.cache import cache

logger = logging.getLogger(__name__)


class ProcessingStateManager:
    """Manages pipeline processing state in Redis.

    Pipeline stages:
    - raw_text: Document text extraction via LLMWhisperer
    - summary: Document summarization via SummarizerAgent
    - schema: Schema generation via Uniformer + Finalizer
    - prompt: Initial prompt generation via PromptArchitect
    - extraction: Batch extraction on all documents

    Statuses:
    - pending: Not started
    - in_progress: Currently processing
    - completed: Successfully completed
    - failed: Failed with error
    """

    STAGES = ["raw_text", "summary", "schema", "prompt", "extraction"]
    STATUSES = ["pending", "in_progress", "completed", "failed"]

    # TTL for state data (24 hours)
    STATE_TTL = 60 * 60 * 24

    @staticmethod
    def _get_key(project_id: UUID, stage: str) -> str:
        """Generate Redis key for a project stage.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage name

        Returns:
            str: Redis key
        """
        return f"agentic:pipeline:{project_id}:{stage}"

    @staticmethod
    def set_stage_status(
        project_id: UUID,
        stage: str,
        status: str,
        progress: int = 0,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Set the status for a specific pipeline stage.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage (must be in STAGES)
            status: Status (must be in STATUSES)
            progress: Progress percentage (0-100)
            message: Human-readable status message
            metadata: Optional additional data

        Returns:
            bool: True if successful
        """
        if stage not in ProcessingStateManager.STAGES:
            logger.error(f"Invalid stage: {stage}")
            return False

        if status not in ProcessingStateManager.STATUSES:
            logger.error(f"Invalid status: {status}")
            return False

        key = ProcessingStateManager._get_key(project_id, stage)
        data = {
            "stage": stage,
            "status": status,
            "progress": min(100, max(0, progress)),
            "message": message,
            "metadata": metadata or {},
        }

        try:
            cache.set(key, json.dumps(data), ProcessingStateManager.STATE_TTL)
            logger.debug(f"Set stage status: {project_id}/{stage} -> {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to set stage status: {e}")
            return False

    @staticmethod
    def get_stage_status(project_id: UUID, stage: str) -> Optional[Dict[str, Any]]:
        """Get the status for a specific pipeline stage.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage name

        Returns:
            Dict with stage status or None
        """
        if stage not in ProcessingStateManager.STAGES:
            return None

        key = ProcessingStateManager._get_key(project_id, stage)

        try:
            data = cache.get(key)
            if data:
                return json.loads(data)
            # Default to pending if no state exists
            return {
                "stage": stage,
                "status": "pending",
                "progress": 0,
                "message": "Not started",
                "metadata": {},
            }
        except Exception as e:
            logger.error(f"Failed to get stage status: {e}")
            return None

    @staticmethod
    def get_pipeline_status(project_id: UUID) -> Dict[str, Any]:
        """Get the status of all pipeline stages for a project.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with all stage statuses
        """
        pipeline_status = {
            "project_id": str(project_id),
            "stages": {},
        }

        for stage in ProcessingStateManager.STAGES:
            status = ProcessingStateManager.get_stage_status(project_id, stage)
            if status:
                pipeline_status["stages"][stage] = status

        # Calculate overall progress (average of all stages)
        total_progress = sum(
            s["progress"] for s in pipeline_status["stages"].values()
        )
        overall_progress = total_progress / len(ProcessingStateManager.STAGES)
        pipeline_status["overall_progress"] = round(overall_progress, 2)

        # Determine overall status
        stage_statuses = [s["status"] for s in pipeline_status["stages"].values()]
        if "failed" in stage_statuses:
            pipeline_status["overall_status"] = "failed"
        elif "in_progress" in stage_statuses:
            pipeline_status["overall_status"] = "in_progress"
        elif all(s == "completed" for s in stage_statuses):
            pipeline_status["overall_status"] = "completed"
        else:
            pipeline_status["overall_status"] = "pending"

        return pipeline_status

    @staticmethod
    def reset_pipeline(project_id: UUID) -> bool:
        """Reset all pipeline stages to pending.

        Args:
            project_id: UUID of the project

        Returns:
            bool: True if successful
        """
        try:
            for stage in ProcessingStateManager.STAGES:
                ProcessingStateManager.set_stage_status(
                    project_id,
                    stage,
                    status="pending",
                    progress=0,
                    message="Not started",
                )
            logger.info(f"Reset pipeline for project {project_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset pipeline: {e}")
            return False

    @staticmethod
    def clear_pipeline_state(project_id: UUID) -> bool:
        """Clear all pipeline state for a project (delete from Redis).

        Args:
            project_id: UUID of the project

        Returns:
            bool: True if successful
        """
        try:
            for stage in ProcessingStateManager.STAGES:
                key = ProcessingStateManager._get_key(project_id, stage)
                cache.delete(key)
            logger.info(f"Cleared pipeline state for project {project_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear pipeline state: {e}")
            return False

    @staticmethod
    def mark_stage_complete(
        project_id: UUID, stage: str, message: str = "Completed successfully"
    ) -> bool:
        """Convenience method to mark a stage as completed.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage name
            message: Optional completion message

        Returns:
            bool: True if successful
        """
        return ProcessingStateManager.set_stage_status(
            project_id, stage, status="completed", progress=100, message=message
        )

    @staticmethod
    def mark_stage_failed(
        project_id: UUID, stage: str, error_message: str
    ) -> bool:
        """Convenience method to mark a stage as failed.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage name
            error_message: Error description

        Returns:
            bool: True if successful
        """
        return ProcessingStateManager.set_stage_status(
            project_id, stage, status="failed", progress=0, message=error_message
        )

    @staticmethod
    def start_stage(
        project_id: UUID, stage: str, message: str = "Processing..."
    ) -> bool:
        """Convenience method to mark a stage as in progress.

        Args:
            project_id: UUID of the project
            stage: Pipeline stage name
            message: Optional status message

        Returns:
            bool: True if successful
        """
        return ProcessingStateManager.set_stage_status(
            project_id, stage, status="in_progress", progress=0, message=message
        )
