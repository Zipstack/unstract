from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSettings:
    id: str
    tool_uid: str
    spec: dict[str, Any]
    properties: dict[str, Any]
    is_active: bool
