import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

from file_management.constants import FileInformationKey


@dataclass
class FileInformation:
    name: str
    type: str
    modified_at: Optional[datetime]
    content_type: Optional[str]
    size: int

    def __init__(
        self, file_info: dict[str, Any], file_content_type: Optional[str] = None
    ) -> None:
        self.name = os.path.normpath(file_info[FileInformationKey.FILE_NAME])
        self.type = file_info[FileInformationKey.FILE_TYPE]

        modified_at = file_info.get(FileInformationKey.FILE_LAST_MODIFIED)
        self.modified_at = self.parse_datetime(modified_at) if modified_at else None

        self.content_type = file_content_type
        self.size = file_info[FileInformationKey.FILE_SIZE]

    @staticmethod
    def parse_datetime(dt_string: Optional[Union[str, datetime]]) -> Optional[datetime]:
        if isinstance(dt_string, str):
            return datetime.strptime(dt_string, "%Y-%m-%dT%H:%M:%S.%f%z")
        return dt_string
