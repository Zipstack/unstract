import json
import logging
from datetime import datetime
from typing import Any, Optional

from unstract.workflow_execution.enums import LogType

from unstract.core.constants import LogFieldName

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
    """

    def __init__(
        self,
        execution_id: str,
        organization_id: str,
        timestamp: int,
        log_type: str,
        data: dict[str, Any],
    ):
        self.execution_id: str = execution_id
        self.organization_id: str = organization_id
        self.timestamp: int = timestamp
        self.event_time: datetime = datetime.fromtimestamp(timestamp)
        self.log_type: LogType = log_type
        self.data: dict[str, Any] = data

    @classmethod
    def from_json(cls, json_data: str) -> Optional["LogDataDTO"]:
        try:
            json_data = json.loads(json_data)
            execution_id = json_data.get(LogFieldName.EXECUTION_ID)
            organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
            timestamp = json_data.get(LogFieldName.TIMESTAMP)
            log_type = json_data.get(LogFieldName.TYPE)
            data = json_data.get(LogFieldName.DATA)
            if all((execution_id, organization_id, timestamp, log_type, data)):
                return cls(execution_id, organization_id, timestamp, log_type, data)
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
            }
        )
