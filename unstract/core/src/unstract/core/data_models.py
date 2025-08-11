"""Shared Data Models for Unstract Workflow Execution

This module contains shared dataclasses used across backend and worker services
to ensure type safety and consistent data structures for API communication.
"""

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrganizationContext:
    """Organization context for API requests."""

    organization_id: str
    tenant_id: str | None = None
    subscription_plan: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "subscription_plan": self.subscription_plan,
        }


# File Operation Data Models
@dataclass
class FileHash:
    """Represents a file with its metadata and hash information.

    This is the canonical representation of a file in the Unstract platform,
    used by both backend Django services and worker processes.
    """

    file_path: str
    file_name: str
    source_connection_type: str
    file_hash: str | None = None
    file_size: int | None = None
    provider_file_uuid: str | None = None
    mime_type: str | None = None
    fs_metadata: dict[str, Any] | None = None
    file_destination: tuple[str, str] | None = None  # Destination for MRQ routing
    is_executed: bool = False
    file_number: int | None = None
    is_manualreview_required: bool = False  # Whether this file requires manual review

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_name": self.file_name,
            "source_connection_type": self.source_connection_type,
            "file_destination": self.file_destination,
            "is_executed": self.is_executed,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "provider_file_uuid": self.provider_file_uuid,
            "fs_metadata": self.fs_metadata,
            "file_number": self.file_number,
            "is_manualreview_required": self.is_manualreview_required,
        }

    def to_json(self) -> dict[str, Any]:
        """Alias for to_dict() for backward compatibility."""
        return self.to_dict()

    def to_serialized_json(self) -> str:
        """Serialize the FileHash instance to a JSON string."""
        import json

        return json.dumps(serialize_dataclass_to_dict(self))

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "FileHash":
        """Deserialize a JSON string or dictionary to a FileHash instance."""
        import json

        if isinstance(json_str_or_dict, dict):
            data = json_str_or_dict
        elif isinstance(json_str_or_dict, str):
            data = json.loads(json_str_or_dict)
        else:
            raise ValueError(f"Expected dict or str, got {type(json_str_or_dict)}")

        # Handle file_destination as tuple if it's a list
        if (
            isinstance(data.get("file_destination"), list)
            and len(data["file_destination"]) == 2
        ):
            data["file_destination"] = tuple(data["file_destination"])

        return FileHash(**data)


class SourceConnectionType(str, Enum):
    """Types of source connections supported."""

    FILESYSTEM = "FILESYSTEM"
    API = "API"


class FileListingResult:
    """Result of listing files from a source."""

    def __init__(
        self,
        files: dict[str, FileHash],
        total_count: int,
        connection_type: str,
        is_api: bool = False,
        used_file_history: bool = False,
    ):
        self.files = files
        self.total_count = total_count
        self.connection_type = connection_type
        self.is_api = is_api
        self.used_file_history = used_file_history


# File Operation Constants
class FileOperationConstants:
    """Constants for file operations."""

    READ_CHUNK_SIZE = 4194304  # 4MB chunks for file reading
    MAX_RECURSIVE_DEPTH = 20  # Maximum directory traversal depth
    DEFAULT_MAX_FILES = 100  # Default maximum files to process

    # File pattern defaults
    DEFAULT_FILE_PATTERNS = ["*"]
    ALL_FILES_PATTERN = "*"

    # Common MIME types
    MIME_TYPE_PDF = "application/pdf"
    MIME_TYPE_TEXT = "text/plain"
    MIME_TYPE_JSON = "application/json"
    MIME_TYPE_CSV = "text/csv"


class SourceKey:
    """Unified keys used in source configuration across backend and workers.

    This class provides both camelCase (backend) and snake_case (core) naming conventions
    to ensure compatibility across different parts of the system.
    """

    # Snake case (core/workers preferred)
    FILE_EXTENSIONS = "file_extensions"
    PROCESS_SUB_DIRECTORIES = "process_sub_directories"
    MAX_FILES = "max_files"
    FOLDERS = "folders"
    USE_FILE_HISTORY = "use_file_history"

    # CamelCase (backend compatibility)
    FILE_EXTENSIONS_CAMEL = "fileExtensions"
    PROCESS_SUB_DIRECTORIES_CAMEL = "processSubDirectories"
    MAX_FILES_CAMEL = "maxFiles"

    @classmethod
    def get_file_extensions(cls, config: dict) -> list:
        """Get file extensions from config using both naming conventions."""
        return list(
            config.get(cls.FILE_EXTENSIONS) or config.get(cls.FILE_EXTENSIONS_CAMEL, [])
        )

    @classmethod
    def get_process_sub_directories(cls, config: dict) -> bool:
        """Get process subdirectories setting from config using both naming conventions."""
        return bool(
            config.get(cls.PROCESS_SUB_DIRECTORIES)
            or config.get(cls.PROCESS_SUB_DIRECTORIES_CAMEL, False)
        )

    @classmethod
    def get_max_files(cls, config: dict, default: int = 100) -> int:
        """Get max files setting from config using both naming conventions."""
        return int(config.get(cls.MAX_FILES) or config.get(cls.MAX_FILES_CAMEL, default))

    @classmethod
    def get_folders(cls, config: dict) -> list:
        """Get folders setting from config."""
        return list(config.get(cls.FOLDERS, ["/"]))


def serialize_dataclass_to_dict(obj) -> dict[str, Any]:
    """Helper function to serialize dataclass objects to JSON-compatible dictionaries.

    Handles datetime objects, UUID objects, and other complex types.
    Removes None values from the output.

    Args:
        obj: Dataclass object to serialize

    Returns:
        Dictionary with JSON-compatible values
    """
    from datetime import date, datetime, time
    from uuid import UUID

    def serialize_value(value):
        """Recursively serialize values to JSON-compatible format."""
        if isinstance(value, UUID):
            return str(value)
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, time):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [serialize_value(item) for item in value]
        elif isinstance(value, tuple):
            return [serialize_value(item) for item in value]
        elif isinstance(value, set):
            return [serialize_value(item) for item in value]
        else:
            return value

    data = asdict(obj)
    # Serialize all values and remove None values
    return {k: serialize_value(v) for k, v in data.items() if v is not None}


class ExecutionStatus(Enum):
    """Unified execution status choices for backend and workers.

    This enum is designed to work seamlessly with both Django CharField assignments
    and worker API calls by implementing __str__ to return the enum value.

    Statuses:
        PENDING: The execution's entry has been created in the database.
        EXECUTING: The execution is currently in progress.
        COMPLETED: The execution has been successfully completed.
        STOPPED: The execution was stopped by the user (applicable to step executions).
        ERROR: An error occurred during the execution process.

    Note: This enum aligns with backend workflow_manager.workflow_v2.enums.ExecutionStatus
    """

    PENDING = "PENDING"
    EXECUTING = "EXECUTING"  # Changed from INPROGRESS to match backend
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"  # Added to match backend
    ERROR = "ERROR"  # Changed from FAILED to match backend

    # Keep legacy statuses for backward compatibility during transition
    QUEUED = "QUEUED"  # Legacy - consider deprecated
    CANCELED = "CANCELED"  # Legacy - maps to STOPPED

    def __str__(self):
        """Return enum value for Django CharField compatibility.

        This ensures that Django model assignments like:
        execution.status = ExecutionStatus.PENDING
        will store "PENDING" in the database instead of "ExecutionStatus.PENDING"
        """
        return self.value

    def __repr__(self):
        """Keep standard enum representation for debugging."""
        return f"ExecutionStatus.{self.name}"


# Add Django-compatible choices attribute after class definition
ExecutionStatus.choices = tuple(
    (status.value, status.value) for status in ExecutionStatus
)


# Add the is_completed method as a class method
def _is_completed(cls, status: str) -> bool:
    """Check if the execution status represents a completed state."""
    try:
        status_enum = cls(status)
        return status_enum in [cls.COMPLETED, cls.STOPPED, cls.ERROR]
    except ValueError:
        raise ValueError(f"Invalid status: {status}. Must be a valid ExecutionStatus.")


ExecutionStatus.is_completed = classmethod(_is_completed)


class WorkflowType(Enum):
    """Workflow type choices matching backend models."""

    ETL = "ETL"
    TASK = "TASK"
    API = "API"
    APP = "APP"


class ConnectionType(Enum):
    """Connection types for workflow sources and destinations."""

    FILESYSTEM = "FILESYSTEM"
    API = "API"
    API_DEPLOYMENT = "API_DEPLOYMENT"
    DATABASE = "DATABASE"
    QUEUE = "QUEUE"
    MANUALREVIEW = "MANUALREVIEW"


@dataclass
class FileHashData:
    """Shared data structure for file hash information and metadata.

    This ensures consistency between backend and worker when handling file data,
    providing clear separation between content hashing and filesystem identification.

    FIELD USAGE PATTERNS:

    file_hash (str):
        - PURPOSE: SHA256 hash of actual file content for deduplication and integrity
        - WHEN COMPUTED: During file processing when content is read
        - EXAMPLES: "a7b2c4d5e6f7..." (64-char SHA256 hex)
        - USED FOR: Content-based deduplication, cache keys, integrity verification

    provider_file_uuid (Optional[str]):
        - PURPOSE: Unique identifier assigned by storage provider (GCS, S3, etc.)
        - WHEN COLLECTED: During file listing/metadata collection phase
        - EXAMPLES: GCS generation ID, S3 ETag, file system inode
        - USED FOR: Tracking files in external storage, detecting file changes

    connector_metadata (Dict[str, Any]):
        - PURPOSE: Connector credentials and configuration needed for file access
        - WHEN COLLECTED: During source configuration processing
        - EXAMPLES: GCS project_id, json_credentials; S3 access_key, secret_key
        - USED FOR: File-processing worker to access source files

    connector_id (Optional[str]):
        - PURPOSE: Full connector ID from registry for file access
        - WHEN COLLECTED: During source configuration processing
        - EXAMPLES: "google_cloud_storage|109bbe7b-8861-45eb-8841-7244e833d97b"
        - USED FOR: File-processing worker to instantiate correct connector

    WORKFLOW PATTERNS:
    1. File Listing: provider_file_uuid collected from filesystem metadata
    2. File Processing: file_hash computed from actual content
    3. Deduplication: Both used for different purposes (content vs storage tracking)
    4. Caching: provider_file_uuid for quick existence checks, file_hash for content verification
    5. Worker Handoff: connector_metadata and connector_id for file access
    """

    file_name: str
    file_path: str
    file_hash: str = ""  # SHA256 content hash - computed during file processing
    file_size: int = 0
    mime_type: str = ""
    provider_file_uuid: str | None = (
        None  # Storage provider identifier - collected from metadata
    )
    fs_metadata: dict[str, Any] = field(default_factory=dict)
    source_connection_type: str | None = None
    file_destination: str | None = None
    is_executed: bool = False
    file_number: int | None = None
    # New fields for connector metadata needed by file-processing workers
    connector_metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Connector credentials and settings
    connector_id: str | None = None  # Full connector ID from registry
    use_file_history: bool = False  # Whether to create file history entries for this file
    is_manualreview_required: bool = False  # Whether this file requires manual review

    def __post_init__(self):
        """Validate required fields."""
        if not self.file_name:
            raise ValueError("file_name is required")
        if not self.file_path:
            raise ValueError("file_path is required")
        # Don't validate file_hash here - it can be computed later

    def compute_hash_from_content(self, content: bytes) -> str:
        """Compute SHA256 hash from file content."""
        import hashlib

        hash_value = hashlib.sha256(content).hexdigest()
        self.file_hash = hash_value
        return hash_value

    def compute_hash_from_file(self, file_path: str) -> str:
        """Compute SHA256 hash from file path."""
        import hashlib

        with open(file_path, "rb") as f:
            hash_value = hashlib.sha256(f.read()).hexdigest()
        self.file_hash = hash_value
        return hash_value

    def compute_hash_from_provider_uuid(self) -> str:
        """Use provider_file_uuid as hash if available (for cloud storage).

        DEPRECATED: This method is deprecated. file_hash should only contain
        SHA256 content hash, not provider_file_uuid.
        """
        if self.provider_file_uuid:
            self.file_hash = self.provider_file_uuid
            return self.provider_file_uuid
        return ""

    def ensure_hash(
        self, content: bytes | None = None, file_path: str | None = None
    ) -> str:
        """Ensure file_hash is populated with SHA256 content hash only.

        IMPORTANT: file_hash should ONLY contain SHA256 hash of actual file content.
        It should NEVER contain provider_file_uuid or any other identifier.

        USAGE PATTERN:
        - Workers: Call during file processing when content is available
        - Backend: Call when content hash is needed for deduplication/caching
        - NOT for early metadata collection (use provider_file_uuid instead)

        Args:
            content: File content bytes (preferred - most accurate)
            file_path: Local file path (fallback when content not available)

        Returns:
            SHA256 hex string of file content, or existing hash if already computed

        Raises:
            ValueError: If called without content or file_path when hash is missing
        """
        if self.file_hash:
            return self.file_hash

        # DESIGN FIX: Don't allow parameterless calls that can't compute hash
        if not content and not file_path:
            raise ValueError(
                f"Cannot ensure hash for {self.file_name}: no content or file_path provided. "
                f"Hash must be computed with actual file data."
            )

        # Only compute real content hash from file content or file path
        if content:
            return self.compute_hash_from_content(content)

        if file_path:
            return self.compute_hash_from_file(file_path)

        # This shouldn't be reachable due to check above, but keep for safety
        logger.error(f"Unexpected state in ensure_hash for {self.file_name}")
        return ""

    def has_hash(self) -> bool:
        """Check if file_hash is already populated without attempting to compute it.

        Returns:
            True if file_hash exists, False otherwise
        """
        return bool(self.file_hash)

    def validate_for_api(self):
        """Validate that all required fields are present for API calls.

        VALIDATION RULES:
        - file_name and file_path are always required
        - Either file_hash OR provider_file_uuid must be present for database uniqueness
        - If both are missing, creates temporary fallback to allow worker processing

        FALLBACK BEHAVIOR:
        When both file_hash and provider_file_uuid are missing (e.g., metadata collection failed),
        creates a temporary MD5 hash of file_path to satisfy database constraints.
        The real SHA256 content hash will be computed later during file processing.
        """
        if not self.file_name:
            raise ValueError("file_name is required")
        if not self.file_path:
            raise ValueError("file_path is required")
        if not self.file_hash and not self.provider_file_uuid:
            # GRACEFUL FALLBACK: If both identifiers are missing, create temporary file path hash
            # This allows workers to proceed when metadata collection fails
            # The real SHA256 content hash will be computed during file processing
            import hashlib

            self.file_hash = hashlib.md5(self.file_path.encode()).hexdigest()
            logger.warning(
                f"Created temporary file path hash for {self.file_name} to allow worker processing"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization of complex data types."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileHashData":
        """Create from dictionary and automatically compute hash if missing."""
        instance = cls(
            file_name=data.get("file_name", ""),
            file_path=data.get("file_path", ""),
            file_hash=data.get("file_hash", ""),
            file_size=data.get("file_size", 0),
            mime_type=data.get("mime_type", ""),
            provider_file_uuid=data.get("provider_file_uuid"),
            fs_metadata=data.get("fs_metadata", {}),
            source_connection_type=data.get("source_connection_type"),
            file_destination=data.get("file_destination"),
            is_executed=data.get("is_executed", False),
            file_number=data.get("file_number"),
            connector_metadata=data.get("connector_metadata", {}),
            connector_id=data.get("connector_id"),
            use_file_history=data.get("use_file_history", False),
            is_manualreview_required=data.get("is_manualreview_required", False),
        )

        # If no hash is provided, leave it empty - hash computation requires content or file_path
        # The calling code should provide the hash or call ensure_hash() with proper parameters
        if not instance.file_hash:
            logger.debug(
                f"FileHashData.from_dict: No file_hash provided for {instance.file_name} - leaving empty"
            )

        return instance


@dataclass
class WorkflowFileExecutionData:
    """Shared data structure for workflow file execution.

    This matches the WorkflowFileExecution model in the backend and provides
    type safety for API communication between services.
    """

    id: str | uuid.UUID
    workflow_execution_id: str | uuid.UUID
    file_name: str
    file_path: str
    file_size: int
    file_hash: str
    status: str = ExecutionStatus.PENDING.value
    provider_file_uuid: str | None = None
    mime_type: str = ""
    fs_metadata: dict[str, Any] = field(default_factory=dict)
    execution_error: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

    def __post_init__(self):
        """Validate and normalize fields."""
        # Convert UUIDs to strings for serialization
        if isinstance(self.id, uuid.UUID):
            self.id = str(self.id)
        if isinstance(self.workflow_execution_id, uuid.UUID):
            self.workflow_execution_id = str(self.workflow_execution_id)

        # Validate required fields
        if not self.file_name:
            raise ValueError("file_name is required")
        if not self.file_path:
            raise ValueError("file_path is required")
        # file_hash can be empty initially - gets populated during file processing with SHA256 hash

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.modified_at:
            data["modified_at"] = self.modified_at.isoformat()
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowFileExecutionData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            id=data["id"],
            workflow_execution_id=data["workflow_execution_id"],
            file_name=data["file_name"],
            file_path=data["file_path"],
            file_size=data.get("file_size", 0),
            file_hash=data["file_hash"],
            status=data.get("status", ExecutionStatus.PENDING.value),
            provider_file_uuid=data.get("provider_file_uuid"),
            mime_type=data.get("mime_type", ""),
            fs_metadata=data.get("fs_metadata", {}),
            execution_error=data.get("execution_error"),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
        )

    def update_status(self, status: str, error_message: str | None = None):
        """Update status and error message."""
        self.status = status
        if error_message:
            self.execution_error = error_message
        self.modified_at = datetime.now()


@dataclass
class WorkflowExecutionData:
    """Shared data structure for workflow execution.

    This matches the WorkflowExecution model in the backend.
    """

    id: str | uuid.UUID
    workflow_id: str | uuid.UUID
    workflow_name: str | None = None
    pipeline_id: str | uuid.UUID | None = None
    task_id: str | None = None
    execution_mode: str = "SYNC"
    execution_method: str = "API"
    execution_type: str = "FILE"
    execution_log_id: str | None = None
    status: str = ExecutionStatus.PENDING.value
    result_acknowledged: bool = False
    total_files: int = 0
    error_message: str | None = None
    attempts: int = 0
    execution_time: float | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

    def __post_init__(self):
        """Validate and normalize fields."""
        # Convert UUIDs to strings for serialization
        if isinstance(self.id, uuid.UUID):
            self.id = str(self.id)
        if isinstance(self.workflow_id, uuid.UUID):
            self.workflow_id = str(self.workflow_id)
        if isinstance(self.pipeline_id, uuid.UUID):
            self.pipeline_id = str(self.pipeline_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.modified_at:
            data["modified_at"] = self.modified_at.isoformat()
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowExecutionData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            id=data["id"],
            workflow_id=data["workflow_id"],
            workflow_name=data.get("workflow_name"),
            pipeline_id=data.get("pipeline_id"),
            task_id=data.get("task_id"),
            execution_mode=data.get("execution_mode", "SYNC"),
            execution_method=data.get("execution_method", "API"),
            execution_type=data.get("execution_type", "FILE"),
            execution_log_id=data.get("execution_log_id"),
            status=data.get("status", ExecutionStatus.PENDING.value),
            result_acknowledged=data.get("result_acknowledged", False),
            total_files=data.get("total_files", 0),
            error_message=data.get("error_message"),
            attempts=data.get("attempts", 0),
            execution_time=data.get("execution_time"),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
        )


# Request/Response dataclasses for API operations


@dataclass
class FileExecutionCreateRequest:
    """Request data for creating a workflow file execution."""

    execution_id: str | uuid.UUID
    file_hash: FileHashData
    workflow_id: str | uuid.UUID

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        return {
            "execution_id": str(self.execution_id),
            "file_hash": self.file_hash.to_dict(),
            "workflow_id": str(self.workflow_id),
        }


@dataclass
class FileExecutionStatusUpdateRequest:
    """Request data for updating file execution status."""

    status: str
    error_message: str | None = None
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data = {"status": self.status}
        if self.error_message:
            data["error_message"] = self.error_message
        if self.result:
            data["result"] = self.result
        return data


@dataclass
class FileHistoryData:
    id: str | uuid.UUID
    workflow_id: str | uuid.UUID
    cache_key: str
    provider_file_uuid: str | None = None
    status: str = ExecutionStatus.PENDING.value
    result: str | None = None
    metadata: str | None = None
    error: str | None = None
    file_path: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.modified_at:
            data["modified_at"] = self.modified_at.isoformat()
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileHistoryData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            id=data.get("id"),
            workflow_id=data.get("workflow_id"),
            cache_key=data.get("cache_key"),
            provider_file_uuid=data.get("provider_file_uuid"),
            status=data.get("status", ExecutionStatus.PENDING.value),
            result=data.get("result"),
            metadata=data.get("metadata"),
            error=data.get("error"),
            file_path=data.get("file_path"),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
        )


@dataclass
class FileHistoryCreateRequest:
    """Request data for creating a file history record."""

    status: str
    workflow_id: str | uuid.UUID
    file_history: FileHistoryData
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        return {
            "status": self.status,
            "workflow_id": str(self.workflow_id),
            "file_history": self.file_history.to_dict(),
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileHistoryCreateRequest":
        """Create from dictionary (e.g., API request)."""
        return cls(
            status=data.get("status"),
            workflow_id=data.get("workflow_id"),
            file_history=FileHistoryData.from_dict(data.get("file_history")),
            message=data.get("message"),
        )


# File Processing Batch Dataclasses
# Moved from backend workflow_manager/workflow_v2/dto.py for shared usage


@dataclass
class SourceConfig:
    """Configuration for workflow data sources."""

    connection_type: ConnectionType
    settings: dict[str, Any] = field(default_factory=dict)
    connector_id: str | None = None
    connector_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with string enum values."""
        return {
            "connection_type": self.connection_type.value,
            "settings": self.settings,
            "connector_id": self.connector_id,
            "connector_metadata": self.connector_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceConfig":
        """Create from dictionary with string connection type."""
        connection_type_str = data.get("connection_type", "FILESYSTEM")
        try:
            connection_type = ConnectionType(connection_type_str)
        except ValueError:
            logger.warning(
                f"Unknown connection type: {connection_type_str}, defaulting to FILESYSTEM"
            )
            connection_type = ConnectionType.FILESYSTEM

        return cls(
            connection_type=connection_type,
            settings=data.get("settings", {}),
            connector_id=data.get("connector_id"),
            connector_metadata=data.get("connector_metadata", {}),
        )


@dataclass
class DestinationConfig:
    """Configuration for workflow data destinations."""

    connection_type: ConnectionType
    settings: dict[str, Any] = field(default_factory=dict)
    connector_id: str | None = None
    connector_metadata: dict[str, Any] = field(default_factory=dict)
    is_api: bool = False
    use_file_history: bool = True
    # Additional fields for worker compatibility
    connector_settings: dict[str, Any] = field(default_factory=dict)
    connector_name: str | None = None
    # Source connector fields for manual review and file reading
    source_connector_id: str | None = None
    source_connector_settings: dict[str, Any] = field(default_factory=dict)
    # HITL queue name for API deployments
    hitl_queue_name: str | None = None

    def __post_init__(self):
        """Post-initialization to handle automatic API detection."""
        # Enforce type safety - connection_type must be ConnectionType enum
        if not isinstance(self.connection_type, ConnectionType):
            raise TypeError(
                f"connection_type must be ConnectionType enum, got {type(self.connection_type).__name__}: {self.connection_type}"
            )

        # Determine if this is an API destination based on connection type
        if self.connection_type and "api" in self.connection_type.value.lower():
            self.is_api = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with string enum values."""
        return {
            "connection_type": self.connection_type.value,
            "settings": self.settings,
            "connector_id": self.connector_id,
            "connector_metadata": self.connector_metadata,
            "is_api": self.is_api,
            "use_file_history": self.use_file_history,
            "connector_settings": self.connector_settings,
            "connector_name": self.connector_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DestinationConfig":
        """Create from dictionary with string connection type."""
        connection_type_str = data.get("connection_type", "FILESYSTEM")
        try:
            connection_type = ConnectionType(connection_type_str)
        except ValueError:
            logger.warning(
                f"Unknown connection type: {connection_type_str}, defaulting to FILESYSTEM"
            )
            connection_type = ConnectionType.FILESYSTEM

        return cls(
            connection_type=connection_type,
            settings=data.get("settings", {}),
            connector_id=data.get("connector_id"),
            connector_metadata=data.get("connector_metadata", {}),
            is_api=data.get("is_api", False),
            use_file_history=data.get("use_file_history", True),
            connector_settings=data.get("connector_settings", {}),
            connector_name=data.get("connector_name"),
            source_connector_id=data.get("source_connector_id"),
            source_connector_settings=data.get("source_connector_settings", {}),
            hitl_queue_name=data.get("hitl_queue_name"),
        )


@dataclass
class WorkerFileData:
    """Shared data structure for worker file processing context."""

    workflow_id: str
    execution_id: str
    single_step: bool
    organization_id: str
    pipeline_id: str
    scheduled: bool
    execution_mode: str
    use_file_history: bool
    q_file_no_list: list[int]
    source_config: dict[str, Any] = field(default_factory=dict)
    destination_config: dict[str, Any] = field(default_factory=dict)
    manual_review_config: dict[str, Any] = field(
        default_factory=lambda: {
            "review_required": False,
            "review_percentage": 0,
            "rule_logic": None,
            "rule_json": None,
            "file_decisions": [],  # Pre-calculated boolean decisions for each file
        }
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkerFileData":
        """Create from dictionary (e.g., API request).

        INPUT VALIDATION:
        - data: Must be dictionary with required fields

        VALIDATION ERRORS:
        - TypeError: Input is not a dictionary
        - ValueError: Missing required fields or invalid field values
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"WorkerFileData requires dictionary input, got {type(data).__name__}"
            )

        # Enhanced required field validation
        required_fields = ["workflow_id", "execution_id", "organization_id"]
        missing_fields = [
            field for field in required_fields if field not in data or not data[field]
        ]
        if missing_fields:
            raise ValueError(
                f"WorkerFileData missing or empty required fields: {missing_fields}. "
                f"Provided fields: {list(data.keys())}"
            )

        # Extract only fields that match this dataclass
        from dataclasses import fields

        field_names = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in field_names}

        # Provide defaults for optional fields with validation
        filtered_data.setdefault("single_step", False)
        filtered_data.setdefault("scheduled", False)
        filtered_data.setdefault("execution_mode", "SYNC")
        filtered_data.setdefault("use_file_history", True)
        filtered_data.setdefault("q_file_no_list", [])
        filtered_data.setdefault("pipeline_id", "")

        # Validate field types
        if not isinstance(filtered_data.get("single_step"), bool):
            raise TypeError(
                f"single_step must be boolean, got {type(filtered_data.get('single_step')).__name__}"
            )
        if not isinstance(filtered_data.get("scheduled"), bool):
            raise TypeError(
                f"scheduled must be boolean, got {type(filtered_data.get('scheduled')).__name__}"
            )
        if not isinstance(filtered_data.get("use_file_history"), bool):
            raise TypeError(
                f"use_file_history must be boolean, got {type(filtered_data.get('use_file_history')).__name__}"
            )
        if not isinstance(filtered_data.get("q_file_no_list"), list):
            raise TypeError(
                f"q_file_no_list must be list, got {type(filtered_data.get('q_file_no_list')).__name__}"
            )

        try:
            return cls(**filtered_data)
        except TypeError as e:
            raise ValueError(
                f"Failed to create WorkerFileData: {str(e)}. Check field types and values."
            ) from e

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)


@dataclass
class FileBatchData:
    """Shared data structure for file batch processing requests."""

    files: list[dict[str, Any]]  # List of file dictionaries
    file_data: WorkerFileData

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileBatchData":
        """Create from dictionary (e.g., Celery task data).

        INPUT VALIDATION:
        - data: Must be dictionary with 'files' list and 'file_data' dict

        VALIDATION ERRORS:
        - TypeError: Input is not a dictionary or has wrong field types
        - ValueError: Missing required fields or invalid field structure
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"FileBatchData requires dictionary input, got {type(data).__name__}"
            )

        # Enhanced field validation
        required_fields = ["file_data", "files"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(
                f"FileBatchData missing required fields: {missing_fields}. "
                f"Provided fields: {list(data.keys())}"
            )

        if not isinstance(data["files"], list):
            raise TypeError(
                f"FileBatchData 'files' must be a list, got {type(data['files']).__name__}"
            )

        # Validate files list structure - Django sends lists due to asdict() serialization
        for i, file_item in enumerate(data["files"]):
            if isinstance(file_item, list):
                # Django backend format after asdict(): [["file_name", file_hash_dict], ...]
                if len(file_item) != 2:
                    raise ValueError(
                        f"FileBatchData 'files[{i}]' list must have exactly 2 elements [file_name, file_hash_dict], got {len(file_item)}"
                    )
                file_name, file_hash_dict = file_item
                if not isinstance(file_name, str):
                    raise TypeError(
                        f"FileBatchData 'files[{i}][0]' (file_name) must be string, got {type(file_name).__name__}"
                    )
                if not isinstance(file_hash_dict, dict):
                    raise TypeError(
                        f"FileBatchData 'files[{i}][1]' (file_hash_dict) must be dictionary, got {type(file_hash_dict).__name__}"
                    )
            elif isinstance(file_item, tuple):
                # Legacy tuple format: [(file_name, file_hash_dict), ...]
                if len(file_item) != 2:
                    raise ValueError(
                        f"FileBatchData 'files[{i}]' tuple must have exactly 2 elements (file_name, file_hash_dict), got {len(file_item)}"
                    )
                file_name, file_hash_dict = file_item
                if not isinstance(file_name, str):
                    raise TypeError(
                        f"FileBatchData 'files[{i}][0]' (file_name) must be string, got {type(file_name).__name__}"
                    )
                if not isinstance(file_hash_dict, dict):
                    raise TypeError(
                        f"FileBatchData 'files[{i}][1]' (file_hash_dict) must be dictionary, got {type(file_hash_dict).__name__}"
                    )
            elif isinstance(file_item, dict):
                # Alternative dictionary format: [{"file_name": "...", "file_path": "..."}, ...]
                required_file_fields = ["file_name", "file_path"]
                missing_file_fields = [
                    field for field in required_file_fields if field not in file_item
                ]
                if missing_file_fields:
                    raise ValueError(
                        f"FileBatchData 'files[{i}]' missing required fields: {missing_file_fields}"
                    )
            else:
                raise TypeError(
                    f"FileBatchData 'files[{i}]' must be a list [file_name, file_hash_dict], tuple (file_name, file_hash_dict), or dictionary, got {type(file_item).__name__}"
                )

        try:
            file_data = WorkerFileData.from_dict(data["file_data"])
        except Exception as e:
            raise ValueError(
                f"Failed to create WorkerFileData from file_data field: {str(e)}"
            ) from e

        return cls(files=data["files"], file_data=file_data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class FileBatchResult:
    """Shared data structure for file batch processing results."""

    successful_files: int = 0
    failed_files: int = 0
    execution_time: float = 0.0  # Total execution time for all files in batch

    @property
    def total_files(self) -> int:
        """Total number of files processed."""
        return self.successful_files + self.failed_files

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary for API response."""
        return {
            "successful_files": self.successful_files,
            "failed_files": self.failed_files,
            "total_files": self.total_files,  # Include calculated total_files property
            "execution_time": self.execution_time,  # Include batch execution time
        }

    def increment_success(self):
        """Increment successful file count."""
        self.successful_files += 1

    def increment_failure(self):
        """Increment failed file count."""
        self.failed_files += 1

    def add_execution_time(self, time_seconds: float):
        """Add execution time for a file to the batch total."""
        self.execution_time += time_seconds


# Workflow Definition and Endpoint Dataclasses
# Added to support proper serialization of backend workflow definitions


@dataclass
class ConnectorInstanceData:
    """Shared data structure for connector instance information."""

    connector_id: str
    connector_name: str = ""
    connector_metadata: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorInstanceData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            connector_id=data.get("connector_id", ""),
            connector_name=data.get("connector_name", ""),
            connector_metadata=data.get("connector_metadata", {}),
            is_active=data.get("is_active", True),
        )


@dataclass
class WorkflowEndpointConfigData:
    """Shared data structure for workflow endpoint configuration."""

    endpoint_id: str
    endpoint_type: str  # SOURCE or DESTINATION
    connection_type: str  # FILESYSTEM, DATABASE, API, etc.
    configuration: dict[str, Any] = field(default_factory=dict)
    connector_instance: ConnectorInstanceData | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        data = {
            "endpoint_id": self.endpoint_id,
            "endpoint_type": self.endpoint_type,
            "connection_type": self.connection_type,
            "configuration": self.configuration,
            "is_active": self.is_active,
        }
        if self.connector_instance:
            data["connector_instance"] = self.connector_instance.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowEndpointConfigData":
        """Create from dictionary (e.g., API response)."""
        connector_instance = None
        if data.get("connector_instance"):
            connector_instance = ConnectorInstanceData.from_dict(
                data["connector_instance"]
            )

        return cls(
            endpoint_id=data.get("endpoint_id", ""),
            endpoint_type=data.get("endpoint_type", ""),
            connection_type=data.get("connection_type", ""),
            configuration=data.get("configuration", {}),
            connector_instance=connector_instance,
            is_active=data.get("is_active", True),
        )


@dataclass
class WorkflowTypeDetectionData:
    """Shared data structure for workflow type detection results."""

    workflow_type: str  # ETL, TASK, API, APP, DEFAULT
    source_model: str  # 'pipeline' or 'api_deployment' or 'workflow_fallback'
    pipeline_id: str | None = None
    api_deployment_id: str | None = None
    is_api_workflow: bool = False
    is_pipeline_workflow: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowTypeDetectionData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            workflow_type=data.get("workflow_type", "DEFAULT"),
            source_model=data.get("source_model", "workflow_fallback"),
            pipeline_id=data.get("pipeline_id"),
            api_deployment_id=data.get("api_deployment_id"),
            is_api_workflow=data.get("is_api_workflow", False),
            is_pipeline_workflow=data.get("is_pipeline_workflow", False),
        )


@dataclass
class WorkflowDefinitionResponseData:
    """Shared data structure for complete workflow definition API responses.

    This ensures consistent serialization between backend and workers for workflow definitions.
    """

    workflow_id: str
    workflow_name: str
    workflow_type_detection: WorkflowTypeDetectionData
    source_config: WorkflowEndpointConfigData
    destination_config: WorkflowEndpointConfigData
    organization_id: str
    created_at: str | None = None
    modified_at: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return {
            "id": self.workflow_id,  # Match worker expectations for 'id' field
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "workflow_type": self.workflow_type_detection.workflow_type,  # For backward compatibility
            "workflow_type_detection": self.workflow_type_detection.to_dict(),
            "source_config": self.source_config.to_dict(),
            "destination_config": self.destination_config.to_dict(),
            "organization_id": self.organization_id,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinitionResponseData":
        """Create from dictionary (e.g., API response)."""
        # Handle workflow_type_detection field
        type_detection_data = data.get("workflow_type_detection")
        if isinstance(type_detection_data, dict):
            workflow_type_detection = WorkflowTypeDetectionData.from_dict(
                type_detection_data
            )
        else:
            # Fallback: create from basic workflow_type field
            workflow_type_detection = WorkflowTypeDetectionData(
                workflow_type=data.get("workflow_type", "DEFAULT"),
                source_model="workflow_fallback",
            )

        # Handle source_config field
        source_config_data = data.get("source_config", {})
        if isinstance(source_config_data, dict) and source_config_data:
            source_config = WorkflowEndpointConfigData.from_dict(source_config_data)
        else:
            # Empty source config for workflows without source endpoints
            source_config = WorkflowEndpointConfigData(
                endpoint_id="", endpoint_type="SOURCE", connection_type="NONE"
            )

        # Handle destination_config field
        destination_config_data = data.get("destination_config", {})
        if isinstance(destination_config_data, dict) and destination_config_data:
            destination_config = WorkflowEndpointConfigData.from_dict(
                destination_config_data
            )
        else:
            # Empty destination config for workflows without destination endpoints
            destination_config = WorkflowEndpointConfigData(
                endpoint_id="", endpoint_type="DESTINATION", connection_type="NONE"
            )

        return cls(
            workflow_id=data.get("workflow_id") or data.get("id", ""),
            workflow_name=data.get("workflow_name", ""),
            workflow_type_detection=workflow_type_detection,
            source_config=source_config,
            destination_config=destination_config,
            organization_id=data.get("organization_id", ""),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
            is_active=data.get("is_active", True),
        )


# Legacy compatibility function for workers expecting old format
def workflow_definition_to_legacy_format(
    workflow_def: WorkflowDefinitionResponseData,
) -> dict[str, Any]:
    """Convert WorkflowDefinitionResponseData to legacy format expected by existing workers.

    This ensures backward compatibility during the transition period.
    """
    legacy_format = workflow_def.to_dict()

    # Legacy workers expect these specific field mappings
    legacy_format["id"] = workflow_def.workflow_id
    legacy_format["workflow_type"] = workflow_def.workflow_type_detection.workflow_type

    # Simplify config structures for legacy workers
    if workflow_def.source_config.connection_type != "NONE":
        legacy_format["source_config"] = {
            "connection_type": workflow_def.source_config.connection_type,
            "settings": workflow_def.source_config.configuration,
            "connector_id": workflow_def.source_config.connector_instance.connector_id
            if workflow_def.source_config.connector_instance
            else None,
        }
    else:
        legacy_format["source_config"] = {}

    if workflow_def.destination_config.connection_type != "NONE":
        legacy_format["destination_config"] = {
            "connection_type": workflow_def.destination_config.connection_type,
            "settings": workflow_def.destination_config.configuration,
            "connector_id": workflow_def.destination_config.connector_instance.connector_id
            if workflow_def.destination_config.connector_instance
            else None,
        }
    else:
        legacy_format["destination_config"] = {}

    return legacy_format


# Source Connector Configuration Data Models
# These models bridge the gap between backend source.py logic and worker operations


@dataclass
class SourceConnectorConfigData:
    """Shared data structure for source connector configuration.

    This separates connector metadata (credentials, root path) from endpoint
    configuration (folders, patterns, limits) to match backend source.py logic.
    """

    connector_id: str
    connector_metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Credentials, root_path
    endpoint_configuration: dict[str, Any] = field(
        default_factory=dict
    )  # Folders, patterns, limits
    connection_type: str = ""

    def get_root_dir_path(self) -> str:
        """Extract root directory path from connector metadata."""
        return self.connector_metadata.get("path", "")

    def get_folders_to_process(self) -> list[str]:
        """Extract folders to process from endpoint configuration."""
        folders = self.endpoint_configuration.get("folders", ["/"])
        return list(folders) if folders else ["/"]

    def get_file_extensions(self) -> list[str]:
        """Extract file extensions from endpoint configuration."""
        return list(self.endpoint_configuration.get("fileExtensions", []))

    def get_max_files(self) -> int:
        """Extract max files limit from endpoint configuration."""
        return int(self.endpoint_configuration.get("maxFiles", 1000))

    def is_recursive(self) -> bool:
        """Check if subdirectory processing is enabled."""
        return bool(self.endpoint_configuration.get("processSubDirectories", False))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceConnectorConfigData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            connector_id=data.get("connector_id", ""),
            connector_metadata=data.get("connector_metadata", {}),
            endpoint_configuration=data.get("endpoint_configuration", {}),
            connection_type=data.get("connection_type", ""),
        )


@dataclass
class DirectoryValidationData:
    """Shared data structure for directory validation results.

    Handles directory path transformation and validation results for
    consistent processing between backend and workers.
    """

    original_path: str
    transformed_path: str
    is_valid: bool
    error_message: str = ""
    validation_method: str = ""  # 'metadata', 'filesystem', 'fallback'

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectoryValidationData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            original_path=data.get("original_path", ""),
            transformed_path=data.get("transformed_path", ""),
            is_valid=data.get("is_valid", False),
            error_message=data.get("error_message", ""),
            validation_method=data.get("validation_method", ""),
        )


@dataclass
class FilePatternConfigData:
    """Shared data structure for file pattern configuration.

    Handles file extension patterns and validation logic consistent
    with backend source.py pattern processing.
    """

    raw_extensions: list[str] = field(default_factory=list)
    wildcard_patterns: list[str] = field(default_factory=list)
    allowed_mime_types: list[str] = field(default_factory=list)
    blocked_mime_types: list[str] = field(default_factory=list)

    def generate_wildcard_patterns(self) -> list[str]:
        """Generate wildcard patterns from file extensions."""
        if not self.raw_extensions:
            return ["*"]  # Process all files if no extensions specified

        patterns = []
        for ext in self.raw_extensions:
            # Normalize extension format
            ext = ext.lower().strip()
            if not ext.startswith("."):
                ext = "." + ext
            patterns.append(f"*{ext}")

        return patterns

    def matches_pattern(self, file_name: str) -> bool:
        """Check if file matches any of the configured patterns."""
        if not self.wildcard_patterns:
            self.wildcard_patterns = self.generate_wildcard_patterns()

        if not self.wildcard_patterns or "*" in self.wildcard_patterns:
            return True

        import fnmatch

        file_lower = file_name.lower()
        return any(
            fnmatch.fnmatchcase(file_lower, pattern.lower())
            for pattern in self.wildcard_patterns
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilePatternConfigData":
        """Create from dictionary (e.g., API response)."""
        return cls(
            raw_extensions=data.get("raw_extensions", []),
            wildcard_patterns=data.get("wildcard_patterns", []),
            allowed_mime_types=data.get("allowed_mime_types", []),
            blocked_mime_types=data.get("blocked_mime_types", []),
        )


@dataclass
class SourceFileListingRequest:
    """Shared data structure for source file listing requests.

    Standardizes the parameters for file listing operations to ensure
    consistency between backend and worker implementations.
    """

    source_config: SourceConnectorConfigData
    workflow_id: str
    organization_id: str
    execution_id: str | None = None
    use_file_history: bool = True
    max_files: int = 1000
    recursive: bool = True
    file_pattern_config: FilePatternConfigData | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        data = {
            "source_config": self.source_config.to_dict(),
            "workflow_id": self.workflow_id,
            "organization_id": self.organization_id,
            "execution_id": self.execution_id,
            "use_file_history": self.use_file_history,
            "max_files": self.max_files,
            "recursive": self.recursive,
        }
        if self.file_pattern_config:
            data["file_pattern_config"] = self.file_pattern_config.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceFileListingRequest":
        """Create from dictionary (e.g., API request)."""
        file_pattern_config = None
        if data.get("file_pattern_config"):
            file_pattern_config = FilePatternConfigData.from_dict(
                data["file_pattern_config"]
            )

        return cls(
            source_config=SourceConnectorConfigData.from_dict(data["source_config"]),
            workflow_id=data["workflow_id"],
            organization_id=data["organization_id"],
            execution_id=data.get("execution_id"),
            use_file_history=data.get("use_file_history", True),
            max_files=data.get("max_files", 1000),
            recursive=data.get("recursive", True),
            file_pattern_config=file_pattern_config,
        )


@dataclass
class SourceFileListingResponse:
    """Shared data structure for source file listing responses.

    Standardizes the response format for file listing operations to ensure
    consistency between backend and worker implementations.
    """

    files: list[FileHashData] = field(default_factory=list)
    total_files: int = 0
    directories_processed: list[str] = field(default_factory=list)
    validation_results: list[DirectoryValidationData] = field(default_factory=list)
    processing_time: float = 0.0
    errors: list[str] = field(default_factory=list)

    def add_file(self, file_data: FileHashData):
        """Add a file to the response."""
        self.files.append(file_data)
        self.total_files = len(self.files)

    def add_directory(self, directory_path: str):
        """Add a processed directory to the response."""
        if directory_path not in self.directories_processed:
            self.directories_processed.append(directory_path)

    def add_validation_result(self, validation: DirectoryValidationData):
        """Add a directory validation result."""
        self.validation_results.append(validation)

    def add_error(self, error_message: str):
        """Add an error message to the response."""
        self.errors.append(error_message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return {
            "files": [file_data.to_dict() for file_data in self.files],
            "total_files": self.total_files,
            "directories_processed": self.directories_processed,
            "validation_results": [
                validation.to_dict() for validation in self.validation_results
            ],
            "processing_time": self.processing_time,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceFileListingResponse":
        """Create from dictionary (e.g., API response)."""
        files = [FileHashData.from_dict(file_data) for file_data in data.get("files", [])]
        validation_results = [
            DirectoryValidationData.from_dict(val)
            for val in data.get("validation_results", [])
        ]

        return cls(
            files=files,
            total_files=data.get("total_files", 0),
            directories_processed=data.get("directories_processed", []),
            validation_results=validation_results,
            processing_time=data.get("processing_time", 0.0),
            errors=data.get("errors", []),
        )
