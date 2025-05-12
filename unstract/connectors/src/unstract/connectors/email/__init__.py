from unstract.connectors import ConnectorDict
from unstract.connectors.email.register import register_connectors

connectors: ConnectorDict = {}
register_connectors(connectors)
