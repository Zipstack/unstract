import unittest
from unittest.mock import MagicMock, patch

import google.api_core.exceptions

from unstract.connectors.databases.bigquery.bigquery import BigQuery
from unstract.connectors.databases.exceptions import (
    BigQueryForbiddenException,
    BigQueryNotFoundException,
    BigQueryValueException,
    ColumnMissingException,
)


class TestBigQuery(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures that are common across all tests."""
        self.bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":"test_project"}'
                )
            }
        )

    def _execute_query_with_mock_error(self, mock_error, expected_exception):
        """Helper method to execute query with a mocked error.

        Args:
            mock_error: The Google API exception to raise
            expected_exception: The exception class expected to be raised

        Returns:
            The exception context manager from assertRaises
        """
        # Mock the engine and query job
        mock_engine = MagicMock()
        mock_query_job = MagicMock()
        mock_engine.query.return_value = mock_query_job
        mock_query_job.result.side_effect = mock_error

        # Mock get_information_schema to return empty dict
        with patch.object(self.bigquery, "get_information_schema", return_value={}):
            with self.assertRaises(expected_exception) as context:
                self.bigquery.execute_query(
                    engine=mock_engine,
                    sql_query="INSERT INTO test.dataset.table VALUES (@col)",
                    table_name="test.dataset.table",
                    sql_values={"col": "value"},
                    sql_keys=["col"],
                )

        return context

    def test_execute_query_forbidden_billing(self):
        """Test that BigQueryForbiddenException includes actual billing error details."""
        # Create a mock Forbidden exception with billing error message
        billing_error_msg = (
            "403 Billing has not been enabled for this project. "
            "Enable billing at https://console.cloud.google.com/billing"
        )
        mock_error = google.api_core.exceptions.Forbidden(billing_error_msg)
        mock_error.message = billing_error_msg

        # Execute query with mock error
        context = self._execute_query_with_mock_error(
            mock_error, BigQueryForbiddenException
        )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Please check your permissions", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("403 Billing has not been enabled", error_msg)
        self.assertIn("test.dataset.table", error_msg)

    def test_execute_query_forbidden_permission(self):
        """Test that BigQueryForbiddenException includes actual permission error details."""
        # Create a mock Forbidden exception with permission error message
        permission_error_msg = (
            "403 User does not have permission to access table test.dataset.table"
        )
        mock_error = google.api_core.exceptions.Forbidden(permission_error_msg)
        mock_error.message = permission_error_msg

        # Execute query with mock error
        context = self._execute_query_with_mock_error(
            mock_error, BigQueryForbiddenException
        )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("User does not have permission", error_msg)

    def test_execute_query_not_found(self):
        """Test that BigQueryNotFoundException includes actual resource not found details."""
        # Create a mock NotFound exception
        not_found_error_msg = "404 Dataset 'test:dataset' not found"
        mock_error = google.api_core.exceptions.NotFound(not_found_error_msg)
        mock_error.message = not_found_error_msg

        # Execute query with mock error
        context = self._execute_query_with_mock_error(
            mock_error, BigQueryNotFoundException
        )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        self.assertIn("The requested resource was not found", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("404 Dataset", error_msg)
        self.assertIn("test.dataset.table", error_msg)

    def test_exception_empty_detail(self):
        """Test that exceptions handle empty detail gracefully."""
        # Create a mock Forbidden exception with empty message
        mock_error = google.api_core.exceptions.Forbidden("")
        mock_error.message = ""

        # Execute query with mock error
        context = self._execute_query_with_mock_error(
            mock_error, BigQueryForbiddenException
        )

        # Verify the exception message includes default text but not empty "Details:"
        error_msg = str(context.exception.detail)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Please check your permissions", error_msg)
        # When detail is empty, should not have "Details:" section
        self.assertNotIn("Details:", error_msg)

    def test_bad_request_value_error_routes_to_value_exception(self):
        """UN-3176: a BadRequest about the DATA is not a missing column."""
        value_error_msg = (
            "400 Invalid value: cannot round-trip through string representation; "
            "error in PARSE_JSON expression"
        )
        mock_error = google.api_core.exceptions.BadRequest(value_error_msg)
        mock_error.message = value_error_msg

        context = self._execute_query_with_mock_error(
            mock_error, BigQueryValueException
        )

        error_msg = str(context.exception.detail)
        self.assertIn("BigQuery rejected a value", error_msg)
        # The old message sent users to check a schema that was never wrong.
        self.assertNotIn("make sure all the columns exist", error_msg)
        self.assertIn("test.dataset.table", error_msg)

    def test_bad_request_value_error_detected_from_errors_payload_only(self):
        """The marker lives ONLY in the structured payload, never in str(e).

        ``GoogleAPICallError.__str__`` folds an ``errors`` entry into the string
        only when it exposes ``.code``/``.message`` ATTRIBUTES; BigQuery's REST
        path fills ``errors`` with plain dicts, which fail that check. So this
        case is reachable only by the payload loop in ``_is_value_error`` --
        delete that loop and this test fails while every message-based test
        above still passes.
        """
        mock_error = google.api_core.exceptions.BadRequest(
            "400 Request failed",
            errors=[
                {
                    "reason": "invalidQuery",
                    "message": "Cannot round-trip through string representation",
                }
            ],
        )
        mock_error.message = "400 Request failed"

        # Guard the premise: if the marker ever leaks into str(e), this test
        # would pass through the text branch and prove nothing.
        self.assertNotIn("round-trip", str(mock_error).lower())

        context = self._execute_query_with_mock_error(
            mock_error, BigQueryValueException
        )
        self.assertIn("BigQuery rejected a value", str(context.exception.detail))

    def test_bad_request_schema_error_still_routes_to_column_missing(self):
        """A genuine schema BadRequest must keep its existing behaviour."""
        schema_error_msg = "400 no such field: unknown_column"
        mock_error = google.api_core.exceptions.BadRequest(schema_error_msg)
        mock_error.message = schema_error_msg

        context = self._execute_query_with_mock_error(
            mock_error, ColumnMissingException
        )
        self.assertIn("column", str(context.exception.detail).lower())


class TestBigQuerySanitizeForBigQuery(unittest.TestCase):
    """UN-3176: the 15-significant-figure limit for PARSE_JSON compatibility.

    The previous implementation derived a DECIMAL-place count from the value's
    magnitude, which is a different quantity from significant figures. The
    values below are the two classes where the two forms actually disagree --
    an ordinary round number such as 3.14159 is preserved identically by both
    and would pass against either implementation.
    """

    def test_large_magnitude_is_limited_to_15_significant_figures(self):
        """Above 10^15 the old decimal count floored at 0 and kept every digit."""
        self.assertEqual(
            BigQuery._sanitize_for_bigquery(1234567890123456.0),
            1234567890123460.0,
        )

    def test_value_just_below_a_power_of_ten_keeps_15_significant_figures(self):
        """``log10`` returns an exact integer here, inflating the magnitude by one.

        The old form therefore asked for one decimal place too few and emitted
        14 significant figures, collapsing this value to 0.0001.
        """
        value = 9.99999999999999e-05
        self.assertEqual(BigQuery._sanitize_for_bigquery(value), value)

    def test_special_values_are_dropped(self):
        """NaN/Inf cannot be represented in JSON and must not reach BigQuery."""
        self.assertIsNone(BigQuery._sanitize_for_bigquery(float("nan")))
        self.assertIsNone(BigQuery._sanitize_for_bigquery(float("inf")))
        self.assertIsNone(BigQuery._sanitize_for_bigquery(float("-inf")))

    def test_zero_and_modest_precision_are_preserved(self):
        self.assertEqual(BigQuery._sanitize_for_bigquery(0.0), 0.0)
        self.assertEqual(BigQuery._sanitize_for_bigquery(0.001228), 0.001228)

    def test_nested_structures_are_sanitized(self):
        self.assertEqual(
            BigQuery._sanitize_for_bigquery(
                {"rows": [{"time": 1760509016.282637}], "name": "x"}
            ),
            {"rows": [{"time": 1760509016.28264}], "name": "x"},
        )


if __name__ == "__main__":
    unittest.main()
