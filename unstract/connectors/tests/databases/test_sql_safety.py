import unittest

from unstract.connectors.databases.sql_safety import (
    QuoteStyle,
    quote_identifier,
    safe_identifier,
    validate_identifier,
)


class TestValidateIdentifier(unittest.TestCase):
    """Tests for validate_identifier() allowlist regex."""

    def test_valid_simple_identifiers(self):
        valid = ["my_table", "users", "Column1", "_private", "table_name_v2", "a"]
        for name in valid:
            self.assertEqual(validate_identifier(name), name)

    def test_valid_hyphenated_identifiers(self):
        valid = ["my-table", "some-long-name", "data-2024"]
        for name in valid:
            self.assertEqual(validate_identifier(name), name)

    def test_valid_dot_qualified_names(self):
        self.assertEqual(
            validate_identifier("schema.table", allow_dots=True), "schema.table"
        )
        self.assertEqual(
            validate_identifier("project.dataset.table", allow_dots=True),
            "project.dataset.table",
        )

    def test_reject_semicolon(self):
        with self.assertRaises(ValueError):
            validate_identifier("public; DROP TABLE users; --")

    def test_reject_single_quote(self):
        with self.assertRaises(ValueError):
            validate_identifier("test' OR '1'='1")

    def test_reject_double_quote(self):
        with self.assertRaises(ValueError):
            validate_identifier('" OR 1=1 --')

    def test_reject_spaces(self):
        with self.assertRaises(ValueError):
            validate_identifier("table name")

    def test_reject_parentheses(self):
        with self.assertRaises(ValueError):
            validate_identifier("x(); DROP TABLE y")

    def test_reject_empty_string(self):
        with self.assertRaises(ValueError):
            validate_identifier("")

    def test_reject_whitespace_only(self):
        with self.assertRaises(ValueError):
            validate_identifier("   ")

    def test_reject_starts_with_digit(self):
        with self.assertRaises(ValueError):
            validate_identifier("1table")

    def test_reject_dots_without_flag(self):
        with self.assertRaises(ValueError):
            validate_identifier("schema.table")

    def test_reject_dot_with_invalid_part(self):
        with self.assertRaises(ValueError):
            validate_identifier("valid.'; DROP TABLE x", allow_dots=True)

    def test_reject_real_world_payloads(self):
        payloads = [
            "public; CREATE TABLE sqli_proof(pwned text); --",
            "public; SELECT pg_ls_dir('/etc'); --",
            "dbo.results' UNION SELECT name, 'a' FROM sysobjects--",
            "results') OR '1'='1' --",
            "x TEXT); DROP TABLE users; CREATE TABLE dummy(y",
        ]
        for payload in payloads:
            with self.assertRaises(ValueError, msg=f"Should reject: {payload}"):
                validate_identifier(payload)


class TestQuoteIdentifier(unittest.TestCase):
    """Tests for quote_identifier() DB-specific quoting."""

    def test_double_quote_style(self):
        self.assertEqual(
            quote_identifier("my_table", QuoteStyle.DOUBLE_QUOTE), '"my_table"'
        )

    def test_double_quote_escapes_embedded(self):
        self.assertEqual(
            quote_identifier('my"table', QuoteStyle.DOUBLE_QUOTE), '"my""table"'
        )

    def test_backtick_style(self):
        self.assertEqual(
            quote_identifier("my_table", QuoteStyle.BACKTICK), "`my_table`"
        )

    def test_backtick_escapes_embedded(self):
        self.assertEqual(
            quote_identifier("my`table", QuoteStyle.BACKTICK), "`my``table`"
        )

    def test_square_bracket_style(self):
        self.assertEqual(
            quote_identifier("my_table", QuoteStyle.SQUARE_BRACKET), "[my_table]"
        )

    def test_square_bracket_escapes_embedded(self):
        self.assertEqual(
            quote_identifier("my]table", QuoteStyle.SQUARE_BRACKET), "[my]]table]"
        )

    def test_hyphenated_name(self):
        self.assertEqual(
            quote_identifier("my-table", QuoteStyle.DOUBLE_QUOTE), '"my-table"'
        )
        self.assertEqual(
            quote_identifier("my-table", QuoteStyle.BACKTICK), "`my-table`"
        )
        self.assertEqual(
            quote_identifier("my-table", QuoteStyle.SQUARE_BRACKET), "[my-table]"
        )


class TestSafeIdentifier(unittest.TestCase):
    """Tests for safe_identifier() — validate + quote combined."""

    def test_simple_identifier(self):
        self.assertEqual(safe_identifier("users", QuoteStyle.DOUBLE_QUOTE), '"users"')
        self.assertEqual(safe_identifier("users", QuoteStyle.BACKTICK), "`users`")
        self.assertEqual(
            safe_identifier("users", QuoteStyle.SQUARE_BRACKET), "[users]"
        )

    def test_dot_qualified_identifier(self):
        result = safe_identifier(
            "project.dataset.table", QuoteStyle.BACKTICK, allow_dots=True
        )
        self.assertEqual(result, "`project`.`dataset`.`table`")

        result = safe_identifier(
            "dbo.my_table", QuoteStyle.SQUARE_BRACKET, allow_dots=True
        )
        self.assertEqual(result, "[dbo].[my_table]")

    def test_injection_rejected(self):
        with self.assertRaises(ValueError):
            safe_identifier("public; DROP TABLE x; --", QuoteStyle.DOUBLE_QUOTE)

    def test_injection_in_qualified_part(self):
        with self.assertRaises(ValueError):
            safe_identifier(
                "valid.'; DROP TABLE x", QuoteStyle.BACKTICK, allow_dots=True
            )

    def test_hyphenated_table(self):
        self.assertEqual(
            safe_identifier("my-table", QuoteStyle.DOUBLE_QUOTE), '"my-table"'
        )


if __name__ == "__main__":
    unittest.main()
