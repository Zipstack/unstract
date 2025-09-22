from unstract.connectors.filesystems.register import register_connectors

from unstract.connectors import ConnectorDict  # type: ignore

from .local_storage.local_storage import *  # noqa: F401, F403

connectors: ConnectorDict = {}
register_connectors(connectors)
