import traceback
import unittest
from unittest.mock import patch

import psycopg2

from unstract.connectors.databases.postgresql.postgresql import PostgreSQL
from unstract.connectors.exceptions import ConnectorError

CONNECT_FAILED = (
    "Error while connecting to DB: Could not connect. If the user name or "
    "password has special characters, percent-encode them."
)


def _connect_error(settings: dict[str, str], error: str) -> ConnectorError:
    """The error of a test whose connection fails with ``error``."""
    with patch("psycopg2.connect", side_effect=psycopg2.OperationalError(error)):
        try:
            PostgreSQL(settings).test_credentials()
        except ConnectorError as exc:
            return exc
    raise AssertionError("The test did not raise ConnectorError")


class TestMalformedConnectionUrl(unittest.TestCase):
    def _assert_hidden(self, url: str, reason: str) -> None:
        with self.assertRaises(ConnectorError) as caught:
            PostgreSQL({"connection_url": url}).test_credentials()

        text = "".join(traceback.format_exception(caught.exception))
        self.assertIn(reason, text)
        self.assertNotIn("INPW", text)

    def test_url_that_cannot_be_parsed_is_reported_as_invalid(self) -> None:
        for url in (
            "postgres:/alice:STANDINPW@db.invalid/prod",
            "postgresql://alice:STAND%ZZINPW@db.invalid/prod",
            "postgresql://alice:STAND%C3INPW@db.invalid/prod",
            "postgresql://alice:STAND\ud800INPW@db.invalid/prod",
        ):
            # ascii() keeps the lone surrogate out of the xdist report.
            with self.subTest(url=ascii(url)):
                with self.assertLogs(PostgreSQL.__module__, "WARNING") as logs:
                    self._assert_hidden(url, "The connection URL is not valid.")

                self.assertNotIn("INPW", "\n".join(logs.output))

    def test_misread_password_stays_out_of_the_error_and_its_traceback(self) -> None:
        for url in (
            "postgresql://alice:INPW/INPW@db.invalid/prod",
            "postgresql://alice:INPW@INPW@db.invalid/prod",
            "postgresql://alice:INPW@INPW?target_session_attrs=INPW@db.invalid/prod",
            "postgresql://db.invalid?user=alice&password=INPW@INPW",
            "postgresql://alice:INPW/prod",
            "postgresql://alice:INPW,db.invalid/prod",
            "postgresql://alice:INPW\0INPW@db.invalid/prod",
        ):
            echo = psycopg2.OperationalError(f'could not translate host name "{url}"')
            with self.subTest(url=url), patch("psycopg2.connect", side_effect=echo):
                with self.assertLogs(PostgreSQL.__module__, "WARNING") as logs:
                    self._assert_hidden(url, CONNECT_FAILED)

            self.assertNotIn("INPW", "\n".join(logs.output))

    def test_bad_port_with_no_at_sign_stays_out_of_the_error(self) -> None:
        for port in ("0", "65536", "123456"):
            with self.subTest(port=port), self.assertRaises(ConnectorError) as caught:
                PostgreSQL(
                    {"connection_url": f"postgresql://alice.invalid:{port}/prod"}
                ).test_credentials()

            self.assertEqual(caught.exception.message, CONNECT_FAILED)


class TestConnectionFailureReason(unittest.TestCase):
    def test_real_failure_keeps_its_reason(self) -> None:
        for settings in (
            {"connection_url": "postgresql://alice:pw@db.invalid:5432/prod"},
            {"connection_url": "postgresql://alice:pw@db.invalid:65535/prod"},
            {"connection_url": "postgresql://alice:pw@db.invalid:000080/prod"},
            {"connection_url": "postgresql://alice:pa%40ss@db.invalid/prod"},
            {"connection_url": "postgresql://alice:pw@db1.invalid:5432,db2.invalid:5433/prod"},
            {"connection_url": "postgresql://db1.invalid:1,db2.invalid:65535/prod?user=alice&password=pw"},
            {"connection_url": "host=db.invalid user=alice password=pa@ss dbname=prod"},
            {
                "user": "alice",
                "password": "pw",
                "host": "db.invalid",
                "port": "5432",
                "database": "prod",
            },
        ):
            with self.subTest(settings=settings):
                self.assertEqual(
                    _connect_error(settings, "connection refused").message,
                    "Error while connecting to DB: connection refused",
                )

    def test_error_that_is_not_about_the_url_keeps_its_reason(self) -> None:
        # A server whose error text isn't UTF-8 fails the decode.
        error = UnicodeDecodeError("utf-8", b"\xfc", 0, 1, "invalid start byte")
        for settings in (
            {"connection_url": "postgresql://alice:pw@db.invalid/prod"},
            {
                "user": "alice",
                "password": "pw",
                "host": "db.invalid",
                "port": "5432",
                "database": "prod",
            },
        ):
            with self.subTest(settings=settings):
                with patch("psycopg2.connect", side_effect=error):
                    with self.assertRaises(ConnectorError) as caught:
                        PostgreSQL(settings).test_credentials()

                self.assertIn("can't decode byte 0xfc", caught.exception.message)

    def test_mistyped_port_after_the_at_sign_keeps_its_reason(self) -> None:
        for port, reason in (
            ("PORT", 'invalid integer value "PORT"'),
            ("543200", 'invalid port number: "543200"'),
        ):
            url = f"postgresql://alice:pw@db.invalid:{port}/prod"
            with self.subTest(port=port):
                with self.assertRaises(ConnectorError) as caught:
                    PostgreSQL({"connection_url": url}).test_credentials()

                self.assertIn(reason, caught.exception.message)

    def test_url_that_may_be_misread_does_not_claim_to_be_invalid(self) -> None:
        for url in (
            "postgresql://alice:pa?ss@db.invalid/prod",
            "postgresql://alice:pw@db.invalid/my@db",
            "postgresql://db.invalid/prod?user=sa@proj.iam&password=pw",
            "postgresql://alice:12/INPW@db.invalid/prod",
        ):
            with self.subTest(url=url):
                error = _connect_error({"connection_url": url}, "INPW echoed")
                self.assertEqual(error.message, CONNECT_FAILED)
