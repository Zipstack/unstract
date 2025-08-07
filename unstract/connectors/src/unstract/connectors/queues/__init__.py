from unstract.connectors.constants import ConnectorDict
from unstract.connectors.queues.register import register_connectors

connectors: ConnectorDict = {}
register_connectors(connectors)
