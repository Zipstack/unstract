import traceback
import unittest
from unittest.mock import patch

import psycopg2

from unstract.connectors.databases.postgresql.postgresql import PostgreSQL
from unstract.connectors.exceptions import ConnectorError


class TestMalformedConnectionUrl(unittest.TestCase):
    def test_password_stays_out_of_the_error_and_its_traceback(self) -> None:
        for url in (
            "postgres:/alice:STANDINPW@db.invalid/prod",
            "postgresql://alice:STAND%ZZINPW@db.invalid/prod",
            "postgresql://alice:INPW/INPW@db.invalid/prod",
            "postgresql://alice:INPW@INPW@db.invalid/prod",
            "postgresql://alice:INPW@INPW?target_session_attrs=INPW@db.invalid/prod",
            "postgresql://db.invalid?user=alice&password=INPW@INPW",
            "postgresql://alice:INPW/prod",
            "postgresql://alice:INPW,db.invalid/prod",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ConnectorError) as caught:
                    PostgreSQL({"connection_url": url}).test_credentials()

                text = "".join(traceback.format_exception(caught.exception))
                self.assertIn("The connection URL is not valid.", text)
                self.assertNotIn("INPW", text)


class TestConnectionFailureReason(unittest.TestCase):
    def test_real_failure_keeps_its_reason(self) -> None:
        for settings in (
            {"connection_url": "postgresql://alice:pw@db.invalid:5432/prod"},
            {"connection_url": "postgresql://alice:pa%40ss@db.invalid/prod"},
            {"connection_url": "postgresql://alice:pw@db1.invalid:5432,db2.invalid:5433/prod"},
            {"connection_url": "host=db.invalid user=alice password=pa@ss dbname=prod"},
            {
                "user": "alice",
                "password": "pw",
                "host": "db.invalid",
                "port": "5432",
                "database": "prod",
            },
        ):
            with (
                self.subTest(settings=settings),
                patch(
                    "psycopg2.connect",
                    side_effect=psycopg2.OperationalError("connection refused"),
                ),
                self.assertRaises(ConnectorError) as caught,
            ):
                PostgreSQL(settings).test_credentials()

            self.assertEqual(
                caught.exception.message,
                "Error while connecting to DB: connection refused",
            )
