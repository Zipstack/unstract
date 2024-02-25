import unittest

from unstract.connectors.databases.redshift.redshift import Redshift


class TestRedshift(unittest.TestCase):
    def test_user_name_and_password(self):
        redshift = Redshift(
            {
                "user": "awsuser",
                "password": "PASSWORD",
                "host": "redshift-cluster-1.redshift.amazonaws.com",
                "port": "5439",
                "database": "dev",
            }
        )
        query = (
            "SELECT userid, username, firstname, lastname, city, state, email,"
            "phone, likesports, liketheatre, likeconcerts, likejazz,"
            "likeclassical, likeopera, likerock, likevegas, likebroadway,"
            "likemusicals FROM users limit 10"
        )
        cursor = redshift.get_engine().cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        for c in results:
            print(c)

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
