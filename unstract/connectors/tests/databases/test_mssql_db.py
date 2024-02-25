import unittest

from unstract.connectors.databases.mssql.mssql import MSSQL


class TestMSSQL(unittest.TestCase):
    def test_user_name_and_password(self):
        mssql = MSSQL(
            {
                "user": "sa",
                "password": "Ascon@123",
                "server": "localhost",
                "port": "1433",
                "database": "testdb",
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
