import json
from dataclasses import dataclass
from typing import Any


@dataclass
class FileHash:
    file_path: str
    file_hash: str
    file_name: str
    source_connection_type: str
    is_executed: bool = False

    def to_json(self):
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "file_name": self.file_name,
            "source_connection_type": self.source_connection_type,
            "is_executed": self.is_executed,
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
