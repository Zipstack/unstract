from unstract.connectors import ConnectorDict  # type: ignore
from unstract.connectors.databases.register import register_connectors

connectors: ConnectorDict = {}
register_connectors(connectors)
