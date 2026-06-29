import os
import unittest

from unstract.connectors.databases.snowflake.snowflake import SnowflakeDB


class TestSnowflakeDB(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("SNOWFLAKE_TEST_PASSWORD"),
        "Integration test requires a live Snowflake account and SNOWFLAKE_TEST_* env vars",
    )
    def test_something(self):
        sf = SnowflakeDB(
            {
                "user": os.environ["SNOWFLAKE_TEST_USER"],
                "password": os.environ["SNOWFLAKE_TEST_PASSWORD"],
                "account": os.environ["SNOWFLAKE_TEST_ACCOUNT"],
                "database": os.environ.get("SNOWFLAKE_TEST_DATABASE", "RESUME_COLLECTION"),
                "schema": os.environ.get("SNOWFLAKE_TEST_SCHEMA", "PUBLIC"),
                "warehouse": os.environ.get("SNOWFLAKE_TEST_WAREHOUSE", "COMPUTE_WH"),
                "role": os.environ.get("SNOWFLAKE_TEST_ROLE", ""),
            }
        )
        cursor = sf.get_engine().cursor()
        results = cursor.execute("describe table RESUME")
        for c in results:
            print(c)

        self.assertIsNotNone(results)


if __name__ == "__main__":
    unittest.main()
