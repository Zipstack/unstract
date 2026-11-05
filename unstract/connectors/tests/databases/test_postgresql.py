import traceback
import unittest

from unstract.connectors.databases.postgresql.postgresql import PostgreSQL
from unstract.connectors.exceptions import ConnectorError


class TestMalformedConnectionUrl(unittest.TestCase):
    def test_password_stays_out_of_the_error_and_its_traceback(self) -> None:
        for url in (
            "postgres:/alice:STANDINPW@db.invalid/prod",
            "postgresql://alice:STAND%ZZINPW@db.invalid/prod",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ConnectorError) as caught:
                    PostgreSQL({"connection_url": url}).test_credentials()

                text = "".join(traceback.format_exception(caught.exception))
                self.assertIn("The connection URL is not valid.", text)
                self.assertNotIn("INPW", text)
