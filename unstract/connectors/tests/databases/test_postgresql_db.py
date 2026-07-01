import os
import unittest

import pytest
from unstract.connectors.databases.postgresql.postgresql import PostgreSQL

# Whole module needs live infra/credentials — integration tier only.
pytestmark = pytest.mark.integration


class TestPostgreSqlDB(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("POSTGRESQL_TEST_PASSWORD"),
        "Integration test requires a live Postgres and POSTGRESQL_TEST_* env vars",
    )
    def test_user_name_and_password(self):
        psql = PostgreSQL(
            {
                "user": os.environ.get("POSTGRESQL_TEST_USER", "test"),
                "password": os.environ["POSTGRESQL_TEST_PASSWORD"],
                "host": os.environ.get("POSTGRESQL_TEST_HOST", "localhost"),
                "port": os.environ.get("POSTGRESQL_TEST_PORT", "5432"),
                "database": os.environ.get("POSTGRESQL_TEST_DATABASE", "test7"),
                "schema": os.environ.get("POSTGRESQL_TEST_SCHEMA", "public"),
            }
        )
        query = "SELECT * FROM account_user LIMIT 3"
        cursor = psql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        self.assertTrue(len(results) > 0)

    @unittest.skipUnless(
        os.environ.get("POSTGRESQL_TEST_CONNECTION_URL"),
        "Integration test requires POSTGRESQL_TEST_CONNECTION_URL",
    )
    def test_connection_url(self):
        psql = PostgreSQL(
            {
                "connection_url": os.environ["POSTGRESQL_TEST_CONNECTION_URL"],
            }
        )
        query = "SELECT * FROM users LIMIT 3"
        cursor = psql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
