import logging
from logging import NullHandler
from typing import Any

from unstract.connectors.constants import Common
from unstract.connectors.databases import connectors as db_connectors
from unstract.connectors.filesystems import connectors as fs_connectors
from unstract.connectors.operations import ConnectorOperations
from unstract.connectors.queues import connectors as queue_connectors

logging.getLogger(__name__).addHandler(NullHandler())

ConnectorDict = dict[str, dict[str, Any]]

__all__ = [
    "Common",
    "db_connectors",
    "fs_connectors",
    "ConnectorOperations",
    "queue_connectors",
    "ConnectorDict",
]
