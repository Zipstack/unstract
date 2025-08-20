"""Pipeline Data Models for Workers

Type-safe dataclasses for pipeline API responses to avoid dict parsing issues.
Uses the architectural principles from @unstract/core/data_models.py
"""

from dataclasses import dataclass
from typing import Any

from unstract.core.data_models import serialize_dataclass_to_dict


@dataclass
class PipelineData:
    """Pipeline information returned from internal API.

    This matches the structure returned by the backend's pipeline endpoint.
    """

    id: str
    pipeline_name: str
    workflow: str  # UUID of the associated workflow
    pipeline_type: str = "ETL"
    active: bool = True
    scheduled: bool = False
    cron_string: str | None = None
    run_count: int = 0
    last_run_time: str | None = None
    last_run_status: str | None = None
    is_api: bool = False
    resolved_pipeline_type: str = "ETL"
    resolved_pipeline_name: str = ""
    created_at: str | None = None
    modified_at: str | None = None
    app_id: str | None = None
    app_icon: str | None = None
    app_url: str | None = None
    access_control_bundle_id: str | None = None
    organization: int | None = None
    created_by: int | None = None
    modified_by: int | None = None

    def __post_init__(self):
        """Validate required fields."""
        if not self.id:
            raise ValueError("Pipeline ID is required")
        if not self.workflow:
            raise ValueError("Workflow UUID is required")
        if not self.pipeline_name:
            raise ValueError("Pipeline name is required")

    @property
    def workflow_id(self) -> str:
        """Get workflow UUID (alias for consistency)."""
        return self.workflow

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineData":
        """Create from dictionary (backend API response).

        Args:
            data: Dictionary from backend API

        Returns:
            PipelineData instance

        Raises:
            ValueError: If required fields are missing
            TypeError: If data is not a dictionary
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        # Extract required fields with validation
        pipeline_id = data.get("id")
        if not pipeline_id:
            raise ValueError("Pipeline ID is required in API response")

        workflow = data.get("workflow")
        if not workflow:
            raise ValueError("Workflow UUID is required in API response")

        pipeline_name = data.get("pipeline_name")
        if not pipeline_name:
            raise ValueError("Pipeline name is required in API response")

        return cls(
            id=pipeline_id,
            pipeline_name=pipeline_name,
            workflow=workflow,
            pipeline_type=data.get("pipeline_type", "ETL"),
            active=data.get("active", True),
            scheduled=data.get("scheduled", False),
            cron_string=data.get("cron_string"),
            run_count=data.get("run_count", 0),
            last_run_time=data.get("last_run_time"),
            last_run_status=data.get("last_run_status"),
            is_api=data.get("is_api", False),
            resolved_pipeline_type=data.get("resolved_pipeline_type", "ETL"),
            resolved_pipeline_name=data.get("resolved_pipeline_name", ""),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
            app_id=data.get("app_id"),
            app_icon=data.get("app_icon"),
            app_url=data.get("app_url"),
            access_control_bundle_id=data.get("access_control_bundle_id"),
            organization=data.get("organization"),
            created_by=data.get("created_by"),
            modified_by=data.get("modified_by"),
        )


@dataclass
class PipelineApiResponse:
    """Complete pipeline API response structure.

    This wraps the pipeline data and provides proper status handling.
    """

    status: str
    pipeline: PipelineData

    def __post_init__(self):
        """Validate response structure."""
        if self.status not in ["success", "error"]:
            raise ValueError(
                f"Invalid status: {self.status}. Must be 'success' or 'error'"
            )

    @property
    def is_success(self) -> bool:
        """Check if the API response was successful."""
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary matching backend API format."""
        return {"status": self.status, "pipeline": self.pipeline.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineApiResponse":
        """Create from backend API response dictionary.

        Args:
            data: Raw API response from backend

        Returns:
            PipelineApiResponse instance

        Raises:
            ValueError: If response structure is invalid
            TypeError: If data is not a dictionary
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        status = data.get("status")
        if not status:
            raise ValueError("Status is required in API response")

        pipeline_data = data.get("pipeline")
        if not pipeline_data:
            raise ValueError("Pipeline data is required in API response")

        # Create pipeline data object
        pipeline = PipelineData.from_dict(pipeline_data)

        return cls(status=status, pipeline=pipeline)


@dataclass
class APIDeploymentData:
    """API Deployment information for API-type workflows."""

    id: str
    api_name: str
    display_name: str
    pipeline: str  # UUID of the associated pipeline
    pipeline_type: str = "API"
    is_active: bool = True
    created_at: str | None = None
    modified_at: str | None = None

    def __post_init__(self):
        """Validate required fields."""
        if not self.id:
            raise ValueError("API deployment ID is required")
        if not self.pipeline:
            raise ValueError("Pipeline UUID is required")
        if not self.api_name:
            raise ValueError("API name is required")

    @property
    def pipeline_id(self) -> str:
        """Get pipeline UUID (alias for consistency)."""
        return self.pipeline

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIDeploymentData":
        """Create from dictionary (backend API response)."""
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        return cls(
            id=data["id"],
            api_name=data["api_name"],
            display_name=data["display_name"],
            pipeline=data["pipeline"],
            pipeline_type=data.get("pipeline_type", "API"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
        )
