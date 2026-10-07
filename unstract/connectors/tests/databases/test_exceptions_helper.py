import unittest

from unstract.connectors.databases.exceptions_helper import ExceptionHelper


class TestExtractByteException(unittest.TestCase):
    """Tests for ExceptionHelper.extract_byte_exception()."""

    def test_bytes_details(self):
        # pymssql shape: (code, b"message")
        e = Exception(208, b"Invalid object name 'missing'.\n")
        self.assertEqual(
            ExceptionHelper.extract_byte_exception(e), "Invalid object name 'missing'."
        )

    def test_str_details(self):
        # pymysql shape: (code, "message")
        e = Exception(1064, "You have an error in your SQL syntax ")
        self.assertEqual(
            ExceptionHelper.extract_byte_exception(e),
            "You have an error in your SQL syntax",
        )

    def test_single_arg_falls_back_to_message(self):
        e = Exception("connection lost")
        self.assertEqual(ExceptionHelper.extract_byte_exception(e), "connection lost")

    def test_message_is_not_evaluated(self):
        marker = []
        payload = "(1, marker.append('executed') or 'x')"
        e = Exception(payload)
        self.assertEqual(ExceptionHelper.extract_byte_exception(e), payload)
        self.assertEqual(marker, [])


if __name__ == "__main__":
    unittest.main()
