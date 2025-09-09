import json
import os
from unittest.mock import Mock, patch

from django.test import TestCase
from workflow_manager.endpoint_v2.constants import DestinationKey
from workflow_manager.endpoint_v2.destination import DestinationConnector

from unstract.connectors.databases.bigquery import BigQuery


class TestDestinationConnectorBigQuery(TestCase):
    """Integration test for insert_into_db method with real BigQuery connector."""

    def setUp(self) -> None:
        """Set up test data and real BigQuery configuration."""

        # BigQuery connection settings for testing
        service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
        if not service_account_json:
            self.skipTest("SERVICE_ACCOUNT_JSON environment variable not set")

        # Parse the service account JSON
        try:
            service_account_dict = json.loads(service_account_json)
            project_id = service_account_dict.get("project_id")
            if not project_id:
                self.skipTest("project_id not found in service account JSON")
        except json.JSONDecodeError:
            self.skipTest("Invalid JSON in SERVICE_ACCOUNT_JSON environment variable")

        self.bigquery_config = {"json_credentials": service_account_json}

        # Test data that will be inserted into the database
        self.test_data = {"key": "value", "result": "test_result", "status": "success"}
        self.test_metadata = {
            "file_execution_id": "test-file-exec-id",
            "extracted_text": "This is sample extracted text",
            "processing_time": 1.5,
        }
        self.input_file_path = "/path/to/test/file.pdf"

        # BigQuery table format: project.dataset.table
        dataset_name = "temp_dataset"  # Use your dataset name
        self.test_table_name = f"{project_id}.{dataset_name}.output_2"

        # Create real BigQuery connector instance
        self.bigquery_connector = BigQuery(settings=self.bigquery_config)

        # Expected columns based on configuration (BigQuery data types)
        self.expected_columns = {
            "id": "STRING",
            "file_path": "STRING",
            "execution_id": "STRING",
            "data": "JSON",
            "created_at": "TIMESTAMP",
            "created_by": "STRING",
            "metadata": "JSON",
            "error_message": "STRING",
            "status": "STRING",
            "user_field_1": "BOOL",
            "user_field_2": "INT64",
            "user_field_3": "STRING",
        }

    def verify_table_columns(self, table_name: str) -> None:
        """Verify that all expected columns exist in the table with correct types."""
        table_info = self.bigquery_connector.get_information_schema(
            table_name=table_name
        )

        print(f"🔍 Actual table structure for '{table_name}': {table_info}")

        # Check that key columns exist (some columns may be created on-demand)
        required_columns = {
            "id": "STRING",
            "file_path": "STRING",
            "execution_id": "STRING",
            # "data": "STRING",  # Legacy column remains STRING after migration
            # "data_v2": "JSON",  # New JSON column added during migration
            "metadata": "JSON",  # New JSON column added during migration
            "created_at": "TIMESTAMP",
            "created_by": "STRING",
        }

        for expected_column, expected_type in required_columns.items():
            self.assertIn(
                expected_column,
                table_info,
                f"Expected column '{expected_column}' not found in table '{table_name}'",
            )

            actual_type = table_info[expected_column]
            # BigQuery may return lowercase types, so normalize for comparison
            self.assertEqual(
                actual_type.upper(),
                expected_type.upper(),
                f"Column '{expected_column}' has type '{actual_type}', expected '{expected_type}'",
            )

        print(f"✅ All required columns verified in table '{table_name}'")

    def create_mock_workflow(self) -> Mock:
        """Create a mock workflow object."""
        workflow = Mock()
        workflow.id = "test-workflow-id"
        return workflow

    def create_mock_workflow_log(self) -> Mock:
        """Create a mock workflow log object."""
        return Mock()

    def create_real_connector_instance(self) -> Mock:
        """Create connector instance using real BigQuery connector."""
        connector = Mock()
        connector.connector_id = "bigquery|79e1d681-9b8b-4f6b-b972-1a6a095312f4"
        connector.connector_metadata = self.bigquery_config
        # Store reference to real connector for potential future use
        connector._real_bigquery_connector = self.bigquery_connector
        return connector

    def create_mock_endpoint(self, mock_connector_instance: Mock) -> Mock:
        """Create a mock endpoint with real database configuration."""
        endpoint = Mock()
        endpoint.connector_instance = mock_connector_instance
        endpoint.configuration = {
            DestinationKey.TABLE: self.test_table_name,
            DestinationKey.INCLUDE_AGENT: True,
            DestinationKey.INCLUDE_TIMESTAMP: True,
            DestinationKey.AGENT_NAME: "Unstract/DBWriter",
            DestinationKey.COLUMN_MODE: "Write JSON to a single column",
            DestinationKey.SINGLE_COLUMN_NAME: "data",
            DestinationKey.FILE_PATH: "file_path",
            DestinationKey.EXECUTION_ID: "execution_id",
        }
        return endpoint

    def create_destination_connector(
        self, mock_workflow: Mock, mock_workflow_log: Mock, mock_endpoint: Mock
    ) -> DestinationConnector:
        """Create a destination connector with mocked Django dependencies but real DB."""
        with patch(
            "workflow_manager.endpoint_v2.destination.UserContext"
        ) as mock_context:
            mock_context.get_organization_identifier.return_value = "test-org"

            with patch.object(
                DestinationConnector,
                "_get_endpoint_for_workflow",
                return_value=mock_endpoint,
            ):
                with patch.object(
                    DestinationConnector,
                    "_get_source_endpoint_for_workflow",
                    return_value=mock_endpoint,
                ):
                    connector = DestinationConnector(
                        workflow=mock_workflow,
                        execution_id="test-execution-id",
                        workflow_log=mock_workflow_log,
                        use_file_history=False,
                    )
                    return connector

    def test_insert_into_db_happy_path_bigquery(self) -> None:
        """Test successful insertion into real BigQuery database."""
        # Create mock objects for Django models
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()
        mock_endpoint = self.create_mock_endpoint(mock_connector_instance)

        # Create destination connector with real database connection
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

        # Mock only the methods that get data, let database operations be real
        with patch.object(
            destination_connector,
            "get_tool_execution_result",
            return_value=self.test_data,
        ):
            with patch.object(
                destination_connector,
                "get_combined_metadata",
                return_value=self.test_metadata,
            ):
                # This will execute real database operations using BigQuery connector
                destination_connector.insert_into_db(
                    input_file_path=self.input_file_path, error=None
                )

        # Verify that all expected columns were created
        self.verify_table_columns(self.test_table_name)

        print(
            f"✅ Successfully inserted test data into BigQuery table: {self.test_table_name}"
        )

    def test_insert_into_db_with_error_bigquery(self) -> None:
        """Test insertion with error parameter into real BigQuery database."""
        # Create mock objects
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()
        mock_endpoint = self.create_mock_endpoint(mock_connector_instance)

        # Create destination connector
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

        error_message = "Test processing error occurred"

        # Mock the methods that get data
        with patch.object(
            destination_connector,
            "get_tool_execution_result",
            return_value=self.test_data,
        ):
            with patch.object(
                destination_connector,
                "get_combined_metadata",
                return_value=self.test_metadata,
            ):
                # Execute with error parameter
                destination_connector.insert_into_db(
                    input_file_path=self.input_file_path, error=error_message
                )

        # Verify that all expected columns were created
        self.verify_table_columns(self.test_table_name)

        print(
            f"✅ Successfully inserted error data into BigQuery table: {self.test_table_name}"
        )

    def test_bigquery_connector_connection(self) -> None:
        """Test that the BigQuery connector can establish a connection."""
        # Test the real BigQuery connector directly
        try:
            engine = self.bigquery_connector.get_engine()
            self.assertIsNotNone(engine)
            print("✅ BigQuery connector successfully established connection")

            # Test a simple query to verify connection works
            test_query = "SELECT 1 as test_column"
            result = self.bigquery_connector.execute(test_query)
            self.assertIsNotNone(result)
            print("✅ BigQuery connector successfully executed test query")

        except Exception as e:
            self.fail(f"BigQuery connector failed to connect: {str(e)}")
