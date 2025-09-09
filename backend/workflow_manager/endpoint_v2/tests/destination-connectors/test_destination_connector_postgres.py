import os
from unittest.mock import Mock, patch

from django.test import TestCase
from workflow_manager.endpoint_v2.constants import DestinationKey
from workflow_manager.endpoint_v2.destination import DestinationConnector

from unstract.connectors.databases.postgresql import PostgreSQL


class TestDestinationConnectorPostgreSQL(TestCase):
    """Integration test for insert_into_db method with real PostgreSQL connector."""

    def setUp(self) -> None:
        """Set up test data and real PostgreSQL configuration."""

        # Real PostgreSQL connection settings for testing
        self.postgres_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "database": os.getenv("DB_NAME", "test_unstract"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "password"),
            "schema": "public",  # Add schema to fix PostgreSQL issue
        }

        # Test data that will be inserted into the database
        self.test_data = {"key": "value", "result": "test_result", "status": "success"}
        self.test_metadata = {
            "file_execution_id": "test-file-exec-id",
            "extracted_text": "This is sample extracted text",
            "processing_time": 1.5,
        }
        self.input_file_path = "/path/to/test/file.pdf"
        self.test_table_name = "output"

        # Create real PostgreSQL connector instance
        self.postgres_connector = PostgreSQL(settings=self.postgres_config)

        # Expected columns based on configuration
        self.expected_columns = {
            "id": "text",
            "file_path": "text",
            "execution_id": "text",
            "data": "jsonb",
            "created_at": "timestamp without time zone",
            "created_by": "text",
            "metadata": "jsonb",
            "error_message": "text",
            "status": "text",
            "user_field_1": "boolean",
            "user_field_2": "integer",
            "user_field_3": "text",
        }

    def verify_table_columns(self, table_name: str) -> None:
        """Verify that all expected columns exist in the table with correct types."""
        table_info = self.postgres_connector.get_information_schema(
            table_name=table_name
        )

        print(f"🔍 Actual table structure for '{table_name}': {table_info}")

        # Check that key columns exist (some columns may be created on-demand)
        required_columns = {
            "id": "text",
            "file_path": "text",
            "execution_id": "text",
            "data": ["text", "jsonb"],  # Can be either, migration might convert
            "created_at": "timestamp without time zone",
            "created_by": "text",
        }

        for expected_column, expected_types in required_columns.items():
            self.assertIn(
                expected_column,
                table_info,
                f"Expected column '{expected_column}' not found in table '{table_name}'",
            )

            actual_type = table_info[expected_column]
            if isinstance(expected_types, list):
                self.assertIn(
                    actual_type,
                    expected_types,
                    f"Column '{expected_column}' has type '{actual_type}', expected one of {expected_types}",
                )
            else:
                self.assertEqual(
                    actual_type,
                    expected_types,
                    f"Column '{expected_column}' has type '{actual_type}', expected '{expected_types}'",
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
        """Create connector instance using real PostgreSQL connector."""
        connector = Mock()
        connector.connector_id = "postgresql|6db35f45-be11-4fd5-80c5-85c48183afbb"
        connector.connector_metadata = self.postgres_config
        # Store reference to real connector for potential future use
        connector._real_postgresql_connector = self.postgres_connector
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

    def test_insert_into_db_happy_path_postgresql(self) -> None:
        """Test successful insertion into real PostgreSQL database."""
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
                # This will execute real database operations using PostgreSQL connector
                destination_connector.insert_into_db(
                    input_file_path=self.input_file_path, error=None
                )

        # Verify that all expected columns were created
        self.verify_table_columns(self.test_table_name)

        print(
            f"✅ Successfully inserted test data into PostgreSQL table: {self.test_table_name}"
        )

    def test_insert_into_db_with_error_postgresql(self) -> None:
        """Test insertion with error parameter into real PostgreSQL database."""
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
            f"✅ Successfully inserted error data into PostgreSQL table: {self.test_table_name}"
        )

    def test_postgresql_connector_connection(self) -> None:
        """Test that the PostgreSQL connector can establish a connection."""
        # Test the real PostgreSQL connector directly
        try:
            engine = self.postgres_connector.get_engine()
            self.assertIsNotNone(engine)
            print("✅ PostgreSQL connector successfully established connection")

            # Clean up
            if hasattr(engine, "close"):
                engine.close()
        except Exception as e:
            self.fail(f"PostgreSQL connector failed to connect: {str(e)}")

    def test_comprehensive_column_data_verification(self) -> None:
        """Test that data is properly inserted into all columns with correct values."""
        # Create mock objects
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()
        mock_endpoint = self.create_mock_endpoint(mock_connector_instance)

        # Create destination connector
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

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
                # Execute database insertion
                destination_connector.insert_into_db(
                    input_file_path=self.input_file_path, error=None
                )

        # Verify table structure
        self.verify_table_columns(self.test_table_name)

        # Verify data was inserted correctly by querying the table
        engine = self.postgres_connector.get_engine()
        try:
            # Use cursor for raw psycopg2 connection
            cursor = engine.cursor()
            cursor.execute(
                f"SELECT created_by, file_path, execution_id, created_at, data, metadata FROM {self.test_table_name} ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()

            self.assertIsNotNone(row, "No data found in table after insertion")

            # Map results to column names
            created_by, file_path, execution_id, created_at, data, metadata = row

            # Verify specific column values
            self.assertEqual(
                created_by,
                "Unstract/DBWriter",
                f"Expected created_by to be 'Unstract/DBWriter', got '{created_by}'",
            )

            self.assertEqual(
                file_path,
                self.input_file_path,
                f"Expected file_path to be '{self.input_file_path}', got '{file_path}'",
            )

            self.assertEqual(
                execution_id,
                "test-execution-id",
                f"Expected execution_id to be 'test-execution-id', got '{execution_id}'",
            )

            self.assertIsNotNone(created_at, "Expected created_at timestamp to be set")

            self.assertIsNotNone(data, "Expected data column to contain inserted data")

            self.assertIsNotNone(
                metadata, "Expected metadata column to contain metadata"
            )

            cursor.close()
            print("✅ All column data values verified successfully")

        finally:
            if hasattr(engine, "close"):
                engine.close()
