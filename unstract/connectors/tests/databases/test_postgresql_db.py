import unittest

from unstract.connectors.databases.postgresql.postgresql import PostgreSQL


class TestPostgreSqlDB(unittest.TestCase):
    def test_user_name_and_password(self):
        psql = PostgreSQL(
            {
                "user": "test",
                "password": "ascon",
                "host": "localhost",
                "port": "5432",
                "database": "test7",
                "schema": "public",
            }
        )
        query = "SELECT * FROM account_user LIMIT 3"
        cursor = psql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)

        self.assertTrue(len(results) > 0)

    def test_connection_url(self):
        connection_url = (
            "postgres://iamali003:FeQhupi41INg@ep-crimson-wind-434055"
            ".us-east-2.aws.neon.tech/neondb"
        )
        psql = PostgreSQL(
            {
                "connection_url": connection_url,
            }
        )
        query = "SELECT * FROM users LIMIT 3"
        cursor = psql.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
