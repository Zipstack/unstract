from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolSettings:
    id: str
    tool_uid: str
    spec: dict[str, Any]
    properties: dict[str, Any]
    runtime_variables: dict[str, Any]
    is_active: bool
    image_name: str
    image_tag: str


@dataclass
class ConnectorInstance:
    connector_id: str
    connector_name: str
    connector_type: str
    connector_mode: str
    connector_metadata: dict[str, Any]


@dataclass
class ToolInstance:
    id: str
    tool_id: str
    step: int
    workflow: str
    metadata: dict[str, Any]
    properties: Optional[dict[str, Any]] = None
    image_name: Optional[dict[str, Any]] = None
    image_tag: Optional[dict[str, Any]] = None


@dataclass
class WorkflowDto:
    id: str
    settings: dict[str, Any]
