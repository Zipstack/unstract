from dataclasses import dataclass
from typing import Any


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
    properties: dict[str, Any] | None = None
    image_name: dict[str, Any] | None = None
    image_tag: dict[str, Any] | None = None


@dataclass
class WorkflowDto:
    id: str
