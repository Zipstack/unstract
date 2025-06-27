from dataclasses import dataclass
from typing import Any

from .postman_collection import HighlightPostmanDto


@dataclass
class MetadataDto:
    name: str
    class_name: Any
    is_active: bool


metadata = {
    "PostmanCollection": MetadataDto(
        name=HighlightPostmanDto.__name__,
        class_name=HighlightPostmanDto,
        is_active=True,
    )
}
