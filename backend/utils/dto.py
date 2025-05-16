from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from django.utils import timezone as dj_timezone

from unstract.core.constants import LogFieldName
from unstract.workflow_execution.enums import LogType

logger = logging.getLogger(__name__)


class LogDataDTO:
    """Log data DTO
    DTO for log data to store to QUEUE
    Attributes:
        execution_id: execution id
        organization_id: organization id
        timestamp: timestamp
        log_type: log type
        data: log data
        file_execution_id: Id for the file execution
    """

    def __init__(
        self,
        execution_id: str,
        organization_id: str,
        timestamp: int,
        log_type: str,
        data: dict[str, Any],
        file_execution_id: str | None = None,
    ):
        self.execution_id: str = execution_id
        self.file_execution_id: str | None = file_execution_id
        self.organization_id: str = organization_id
        self.timestamp: int = timestamp
        self.event_time: datetime = dj_timezone.make_aware(
            datetime.fromtimestamp(timestamp), UTC
        )
        self.log_type: LogType = log_type
        self.data: dict[str, Any] = data

    @classmethod
    def from_json(cls, json_data: str) -> LogDataDTO | None:
        try:
            json_data = json.loads(json_data)
            execution_id = json_data.get(LogFieldName.EXECUTION_ID)
            file_execution_id = json_data.get(LogFieldName.FILE_EXECUTION_ID)
            organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
            timestamp = json_data.get(LogFieldName.TIMESTAMP)
            log_type = json_data.get(LogFieldName.TYPE)
            data = json_data.get(LogFieldName.DATA)
            if all((execution_id, organization_id, timestamp, log_type, data)):
                return cls(
                    execution_id=execution_id,
                    file_execution_id=file_execution_id,
                    organization_id=organization_id,
                    timestamp=timestamp,
                    log_type=log_type,
                    data=data,
                )
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Invalid log data: %s", json_data)
        return None

    def to_json(self) -> str:
        return json.dumps(
            {
                LogFieldName.EXECUTION_ID: self.execution_id,
                LogFieldName.ORGANIZATION_ID: self.organization_id,
                LogFieldName.TIMESTAMP: self.timestamp,
                LogFieldName.EVENT_TIME: self.event_time.isoformat(),
                LogFieldName.TYPE: self.log_type,
                LogFieldName.DATA: self.data,
                LogFieldName.FILE_EXECUTION_ID: self.file_execution_id,
            }
        )
