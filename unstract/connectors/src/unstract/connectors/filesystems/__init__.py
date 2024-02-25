from unstract.connectors import ConnectorDict
from unstract.connectors.filesystems.register import register_connectors

connectors: ConnectorDict = {}
register_connectors(connectors)
