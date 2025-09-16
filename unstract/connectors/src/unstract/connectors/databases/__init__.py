from unstract.connectors.databases.register import register_connectors

from unstract.connectors import ConnectorDict  # type: ignore

connectors: ConnectorDict = {}
register_connectors(connectors)
