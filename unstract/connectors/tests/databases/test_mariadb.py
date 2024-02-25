import unittest

from unstract.connectors.databases.mariadb.mariadb import MariaDB


class TestMariaDB(unittest.TestCase):
    def test_user_name_and_password(self):
        mariadb = MariaDB(
            {
                "user": "root",
                "password": "ascon",
                "host": "localhost",
                "port": "3306",
                "database": "testdb",
            }
        )
        query = "SELECT * FROM employees"
        cursor = mariadb.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)
        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
