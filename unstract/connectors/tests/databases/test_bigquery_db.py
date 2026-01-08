import unittest
from unittest.mock import MagicMock, patch

import google.api_core.exceptions

from unstract.connectors.databases.bigquery.bigquery import BigQuery
from unstract.connectors.databases.exceptions import (
    BigQueryForbiddenException,
    BigQueryNotFoundException,
)


class TestBigQuery(unittest.TestCase):

    def test_execute_query_forbidden_billing(self):
        """Test that BigQueryForbiddenException includes actual billing error details."""
        # Create a BigQuery instance
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":"test_project"}'
                )
            }
        )

        # Create a mock Forbidden exception with billing error message
        billing_error_msg = (
            "403 Billing has not been enabled for this project. "
            "Enable billing at https://console.cloud.google.com/billing"
        )
        mock_error = google.api_core.exceptions.Forbidden(billing_error_msg)
        mock_error.message = billing_error_msg

        # Mock the engine and query job
        mock_engine = MagicMock()
        mock_query_job = MagicMock()
        mock_engine.query.return_value = mock_query_job
        mock_query_job.result.side_effect = mock_error

        # Mock get_information_schema to return empty dict (no schema validation needed)
        with patch.object(bigquery, "get_information_schema", return_value={}):
            # Call execute_query and expect BigQueryForbiddenException
            with self.assertRaises(BigQueryForbiddenException) as context:
                bigquery.execute_query(
                    engine=mock_engine,
                    sql_query="INSERT INTO test.dataset.table VALUES (@col)",
                    table_name="test.dataset.table",
                    sql_values={"col": "value"},
                    sql_keys=["col"],
                )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        print("********** error_msg ************ ", error_msg)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Please check your permissions", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("403 Billing has not been enabled", error_msg)
        self.assertIn("test.dataset.table", error_msg)

    def test_execute_query_forbidden_permission(self):
        """Test that BigQueryForbiddenException includes actual permission error details."""
        # Create a BigQuery instance
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":"test_project"}'
                )
            }
        )

        # Create a mock Forbidden exception with permission error message
        permission_error_msg = (
            "403 User does not have permission to access table test.dataset.table"
        )
        mock_error = google.api_core.exceptions.Forbidden(permission_error_msg)
        mock_error.message = permission_error_msg

        # Mock the engine and query job
        mock_engine = MagicMock()
        mock_query_job = MagicMock()
        mock_engine.query.return_value = mock_query_job
        mock_query_job.result.side_effect = mock_error

        # Mock get_information_schema to return empty dict (no schema validation needed)
        with patch.object(bigquery, "get_information_schema", return_value={}):
            # Call execute_query and expect BigQueryForbiddenException
            with self.assertRaises(BigQueryForbiddenException) as context:
                bigquery.execute_query(
                    engine=mock_engine,
                    sql_query="INSERT INTO test.dataset.table VALUES (@col)",
                    table_name="test.dataset.table",
                    sql_values={"col": "value"},
                    sql_keys=["col"],
                )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("User does not have permission", error_msg)

    def test_execute_query_not_found(self):
        """Test that BigQueryNotFoundException includes actual resource not found details."""
        # Create a BigQuery instance
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":"test_project"}'
                )
            }
        )

        # Create a mock NotFound exception
        not_found_error_msg = "404 Dataset 'test:dataset' not found"
        mock_error = google.api_core.exceptions.NotFound(not_found_error_msg)
        mock_error.message = not_found_error_msg

        # Mock the engine and query job
        mock_engine = MagicMock()
        mock_query_job = MagicMock()
        mock_engine.query.return_value = mock_query_job
        mock_query_job.result.side_effect = mock_error

        # Mock get_information_schema to return empty dict (no schema validation needed)
        with patch.object(bigquery, "get_information_schema", return_value={}):
            # Call execute_query and expect BigQueryNotFoundException
            with self.assertRaises(BigQueryNotFoundException) as context:
                bigquery.execute_query(
                    engine=mock_engine,
                    sql_query="INSERT INTO test.dataset.table VALUES (@col)",
                    table_name="test.dataset.table",
                    sql_values={"col": "value"},
                    sql_keys=["col"],
                )

        # Verify the exception message includes both default text and actual error details
        error_msg = str(context.exception.detail)
        self.assertIn("The requested resource was not found", error_msg)
        self.assertIn("Details:", error_msg)
        self.assertIn("404 Dataset", error_msg)
        self.assertIn("test.dataset.table", error_msg)

    def test_exception_empty_detail(self):
        """Test that exceptions handle empty detail gracefully."""
        # Create a BigQuery instance
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":"test_project"}'
                )
            }
        )

        # Create a mock Forbidden exception with empty message
        mock_error = google.api_core.exceptions.Forbidden("")
        mock_error.message = ""

        # Mock the engine and query job
        mock_engine = MagicMock()
        mock_query_job = MagicMock()
        mock_engine.query.return_value = mock_query_job
        mock_query_job.result.side_effect = mock_error

        # Mock get_information_schema to return empty dict (no schema validation needed)
        with patch.object(bigquery, "get_information_schema", return_value={}):
            # Call execute_query and expect BigQueryForbiddenException
            with self.assertRaises(BigQueryForbiddenException) as context:
                bigquery.execute_query(
                    engine=mock_engine,
                    sql_query="INSERT INTO test.dataset.table VALUES (@col)",
                    table_name="test.dataset.table",
                    sql_values={"col": "value"},
                    sql_keys=["col"],
                )

        # Verify the exception message includes default text but not empty "Details:"
        error_msg = str(context.exception.detail)
        self.assertIn("Access forbidden in bigquery", error_msg)
        self.assertIn("Please check your permissions", error_msg)
        # When detail is empty, should not have "Details:" section
        self.assertNotIn("Details:", error_msg)


if __name__ == "__main__":
    unittest.main()
