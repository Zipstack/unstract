import logging
from logging import NullHandler

from unstract.connectors.connection_types import ConnectionType

logging.getLogger(__name__).addHandler(NullHandler())

__all__ = [
    "ConnectionType",
]
