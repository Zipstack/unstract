import unittest

from unstract.core.pubsub_helper import LogHelper as Log


class PubSubHelperTestCase(unittest.TestCase):
    def test_pubsub(self):
        ps1 = Log.publish(
            project_guid="test",
            message=Log.log(stage="COMPILE", message="Compile process started"),
        )
        ps2 = Log.publish(
            project_guid="test",
            message=Log.log(level="ERROR", stage="COMPILE", message="Compile failed"),
        )
        self.assertEqual(ps1, True)
        self.assertEqual(ps2, True)


if __name__ == "__main__":
    unittest.main()
