import logging
import unittest

from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.enums import ConnectorMode

logger = logging.getLogger("unstract.connectors")
logger.setLevel(logging.DEBUG)


class ConnectorkitTestCase(unittest.TestCase):
    def test_connectorkit(self):
        connectorkit = Connectorkit()

        c = connectorkit.get_connector_class_by_name("SnowflakeDB")
        self.assertEqual(c.get_connector_mode(), ConnectorMode.DATABASE)

        c = connectorkit.get_connector_class_by_name("MinioFS")
        self.assertEqual(c.get_connector_mode(), ConnectorMode.FILE_SYSTEM)

        connectors_list = connectorkit.get_connectors_list()
        self.assertIsNotNone(connectors_list)


if __name__ == "__main__":
    unittest.main()
