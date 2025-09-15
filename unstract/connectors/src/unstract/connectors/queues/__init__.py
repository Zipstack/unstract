from unstract.connectors.queues.register import register_connectors

from unstract.connectors import ConnectorDict

connectors: ConnectorDict = {}
register_connectors(connectors)
