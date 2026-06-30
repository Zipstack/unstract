import os
import unittest

import pytest
from unstract.connectors.databases.mysql.mysql import MySQL

# Whole module needs live infra/credentials — integration tier only.
pytestmark = pytest.mark.integration


class TestMySQLDB(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("MYSQL_TEST_PASSWORD"),
        "Integration test requires a live MySQL server and MYSQL_TEST_* env vars",
    )
    def test_user_name_and_password(self):
        mysql = MySQL(
            {
                "user": os.environ.get("MYSQL_TEST_USER", "root"),
                "password": os.environ["MYSQL_TEST_PASSWORD"],
                "host": os.environ.get("MYSQL_TEST_HOST", "localhost"),
                "port": os.environ.get("MYSQL_TEST_PORT", "3306"),
                "database": os.environ.get("MYSQL_TEST_DATABASE", "sakila"),
            }
        )
        query = "SELECT * FROM category"
        cursor = mysql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
