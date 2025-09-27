"""Metadata Models for Workflow Execution

This module provides structured dataclasses for workflow execution metadata,
eliminating hardcoded dictionary creation and providing type safety.
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from .constants import MetaDataKey

logger = logging.getLogger(__name__)


@dataclass
class WorkflowExecutionMetadata:
    """Structured metadata for workflow execution.

    This dataclass provides a type-safe way to handle workflow execution metadata,
    replacing hardcoded dictionary creation with structured data handling.
    """

    source_name: str
    source_hash: str
    organization_id: str
    workflow_id: str
    execution_id: str
    file_execution_id: str
    tags: list[str]
    total_elapsed_time: float | None = None
    tool_metadata: list[dict[str, Any]] = field(default_factory=list)
    llm_profile_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for METADATA.json.

        Returns:
            dict[str, Any]: Dictionary representation compatible with existing format
        """
        result = asdict(self)
        # Remove None values to maintain compatibility with existing code
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowExecutionMetadata":
        """Create metadata instance from existing METADATA.json data.

        Args:
            data: Dictionary data from METADATA.json

        Returns:
            WorkflowExecutionMetadata: Structured metadata instance
        """
        return cls(
            source_name=data.get(MetaDataKey.SOURCE_NAME, ""),
            source_hash=data.get(MetaDataKey.SOURCE_HASH, ""),
            organization_id=data.get(MetaDataKey.ORGANIZATION_ID, ""),
            workflow_id=data.get(MetaDataKey.WORKFLOW_ID, ""),
            execution_id=data.get(MetaDataKey.EXECUTION_ID, ""),
            file_execution_id=data.get(MetaDataKey.FILE_EXECUTION_ID, ""),
            tags=data.get(MetaDataKey.TAGS, []),
            total_elapsed_time=data.get(MetaDataKey.TOTAL_ELAPSED_TIME),
            tool_metadata=data.get(MetaDataKey.TOOL_METADATA, []),
            llm_profile_id=data.get(MetaDataKey.LLM_PROFILE_ID),
        )

    @classmethod
    def create_initial(
        cls,
        source_name: str,
        source_hash: str,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        file_execution_id: str,
        tags: list[str],
        llm_profile_id: str | None = None,
    ) -> "WorkflowExecutionMetadata":
        """Create initial metadata for workflow execution.

        This is an alternative to the hardcoded dictionary creation in add_metadata_to_volume.

        Args:
            source_name: Name of the source file
            source_hash: Hash of the source file
            organization_id: Organization identifier
            workflow_id: Workflow identifier
            execution_id: Execution identifier
            file_execution_id: File execution identifier
            tags: List of tags
            llm_profile_id: Optional LLM profile ID

        Returns:
            WorkflowExecutionMetadata: Initial metadata instance
        """
        return cls(
            source_name=source_name,
            source_hash=source_hash,
            organization_id=organization_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            file_execution_id=file_execution_id,
            tags=tags,
            llm_profile_id=llm_profile_id,
        )

    def update_execution_time(self, execution_time: float) -> None:
        """Update the total execution time.

        Args:
            execution_time: Total execution time in seconds
        """
        self.total_elapsed_time = execution_time
        logger.debug(
            f"Updated execution time to {execution_time:.2f}s for {self.file_execution_id}"
        )

    def add_tool_metadata(self, tool_metadata: dict[str, Any]) -> None:
        """Add tool metadata to the collection.

        Args:
            tool_metadata: Metadata for a single tool execution
        """
        self.tool_metadata.append(tool_metadata)
        logger.debug(f"Added tool metadata for {self.file_execution_id}")

    def get_total_elapsed_time(self) -> float:
        """Get total elapsed time, with fallback to sum of tool times.

        Returns:
            float: Total elapsed time in seconds
        """
        if self.total_elapsed_time is not None:
            return self.total_elapsed_time

        # Fallback: sum of individual tool elapsed times
        total = 0.0
        for tool_meta in self.tool_metadata:
            elapsed = tool_meta.get("elapsed_time", 0)
            if isinstance(elapsed, (int, float)):
                total += elapsed

        return total
