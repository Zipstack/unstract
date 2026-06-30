import os
import unittest

import pytest
from unstract.connectors.databases.mssql.mssql import MSSQL

# Whole module needs live infra/credentials — integration tier only.
pytestmark = pytest.mark.integration


class TestMSSQL(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MSSQL_TEST_PASSWORD"),
        "Integration test requires a live MSSQL server and MSSQL_TEST_* env vars",
    )
    def test_user_name_and_password(self):
        mssql = MSSQL(
            {
                "user": os.environ.get("MSSQL_TEST_USER", "sa"),
                "password": os.environ["MSSQL_TEST_PASSWORD"],
                "server": os.environ.get("MSSQL_TEST_SERVER", "localhost"),
                "port": os.environ.get("MSSQL_TEST_PORT", "1433"),
                "database": os.environ.get("MSSQL_TEST_DATABASE", "testdb"),
            }
        )
        query = "SELECT * FROM Employees"
        cursor = mssql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
