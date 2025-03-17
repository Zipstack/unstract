from dataclasses import dataclass
from typing import Any


@dataclass
class MetadataDto:
    name: str
    class_name: Any
    is_active: bool


metadata = {}
