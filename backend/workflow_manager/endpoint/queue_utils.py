import logging

from typing import Any
from utils.constants import Common
from unstract.connectors.queues.redis import RedisQueue
from unstract.connectors.queues import connectors as queue_connectors

logger = logging.getLogger(__name__)


class QueueUtils:
    @staticmethod
    def get_queue_class(
        connector_id: str, connector_settings: dict[str, Any]
    ) -> RedisQueue:
        connector = queue_connectors[connector_id][Common.METADATA][Common.CONNECTOR]
        connector_class: RedisQueue = connector(connector_settings)
        return connector_class
