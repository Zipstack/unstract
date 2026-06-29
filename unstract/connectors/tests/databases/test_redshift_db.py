import os
import unittest

from unstract.connectors.databases.redshift.redshift import Redshift


class TestRedshift(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("REDSHIFT_TEST_PASSWORD"),
        "Integration test requires a live Redshift cluster and REDSHIFT_TEST_* env vars",
    )
    def test_user_name_and_password(self):
        redshift = Redshift(
            {
                "user": os.environ.get("REDSHIFT_TEST_USER", "awsuser"),
                "password": os.environ["REDSHIFT_TEST_PASSWORD"],
                "host": os.environ["REDSHIFT_TEST_HOST"],
                "port": os.environ.get("REDSHIFT_TEST_PORT", "5439"),
                "database": os.environ.get("REDSHIFT_TEST_DATABASE", "dev"),
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
