import unittest

from unstract.connectors.databases.mysql.mysql import MySQL


class TestMySQLDB(unittest.TestCase):
    def test_user_name_and_password(self):
        mysql = MySQL(
            {
                "user": "visitran",
                "password": "mysqlpass",
                "host": "localhost",
                "port": "3307",
                "database": "sakila",
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
