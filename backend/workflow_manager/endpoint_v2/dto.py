import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FileHash:
    file_path: str
    file_name: str
    source_connection_type: str
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    provider_file_uuid: Optional[str] = None
    mime_type: Optional[str] = None
    fs_metadata: Optional[dict[str, Any]] = None
    file_destination: Optional[tuple[str, str]] = (
        None  # To which destination this file wants to go for MRQ percentage
    )
    is_executed: bool = False

    def to_json(self) -> dict[str, Any]:
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
        }

    @staticmethod
    def from_json(json_str_or_dict: Any) -> "FileHash":
        """Deserialize a JSON string or dictionary to a FileHash instance."""
        if isinstance(json_str_or_dict, dict):
            # If already a dictionary, assume it's in the right format
            data = json_str_or_dict
        else:
            # Otherwise, assume it's a JSON string
            data = json.loads(json_str_or_dict)
        return FileHash(**data)
