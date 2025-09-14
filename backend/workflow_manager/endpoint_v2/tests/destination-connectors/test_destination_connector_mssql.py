import os
from unittest.mock import Mock, patch

from django.test import TestCase
from workflow_manager.endpoint_v2.constants import DestinationKey
from workflow_manager.endpoint_v2.destination import DestinationConnector

from unstract.connectors.databases.mssql import MSSQL


class TestDestinationConnectorMSSQL(TestCase):
    """Integration test for insert_into_db method with real MSSQL connector."""

    def setUp(self) -> None:
        """Set up test data and real MSSQL configuration."""

        # MSSQL connection settings for testing
        required_env_vars = [
            "MSSQL_SERVER",
            "MSSQL_USER",
            "MSSQL_PASSWORD",
            "MSSQL_DATABASE",
        ]

        # Check if all required environment variables are set
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            self.skipTest(
                f"Required MSSQL environment variables not set: {', '.join(missing_vars)}"
            )

        self.mssql_config = {
            "server": os.getenv("MSSQL_SERVER"),
            "port": os.getenv("MSSQL_PORT", "1433"),
            "user": os.getenv("MSSQL_USER"),
            "password": os.getenv("MSSQL_PASSWORD"),
            "database": os.getenv("MSSQL_DATABASE"),
        }

        # Test data that will be inserted into the database
        self.test_data = {"key": "value", "result": "test_result", "status": "success"}
        self.test_metadata = {
            "file_execution_id": "test-file-exec-id",
            "extracted_text": "This is sample extracted text",
            "processing_time": 1.5,
        }
        self.input_file_path = "/path/to/test/file.pdf"

        # MSSQL table naming (use schema.table format)
        self.test_table_name = "test_schema_1.MIGRATION"

        # Create real MSSQL connector instance
        self.mssql_connector = MSSQL(settings=self.mssql_config)

        # Expected columns based on configuration (MSSQL data types)
        self.expected_columns = {
            "id": "NVARCHAR",
            "file_path": "NVARCHAR",
            "execution_id": "NVARCHAR",
            "data": "NVARCHAR",  # Legacy column remains NVARCHAR after migration
            "data_v2": "NVARCHAR",  # New NVARCHAR column added during migration
            "metadata": "NVARCHAR",  # New NVARCHAR column added during migration
            "created_at": "DATETIMEOFFSET",
            "created_by": "NVARCHAR",
            "status": "NVARCHAR",
            "error_message": "NVARCHAR",
            "user_field_1": "BIT",
            "user_field_2": "INT",
            "user_field_3": "NVARCHAR",
        }

    def verify_table_columns(self, table_name: str) -> None:
        """Verify that the table has expected columns with correct data types."""
        table_info = self.mssql_connector.get_information_schema(table_name=table_name)

        print(f"🔍 Actual table structure for '{table_name}': {table_info}")

        # Check that key columns exist (some columns may be created on-demand)
        required_columns = {
            "id": ["NVARCHAR", "TEXT"],  # MSSQL uses NVARCHAR
            "file_path": ["NVARCHAR", "TEXT"],  # MSSQL uses NVARCHAR
            "execution_id": ["NVARCHAR", "TEXT"],  # MSSQL uses NVARCHAR
            "data": ["NVARCHAR", "TEXT"],  # Can be NVARCHAR, migration might convert
            "metadata": [
                "NVARCHAR",
                "TEXT",
            ],  # New NVARCHAR column added during migration
            "created_at": "DATETIMEOFFSET",
            "created_by": ["NVARCHAR", "TEXT"],  # MSSQL uses NVARCHAR
        }

        # Optional columns that may exist in migration scenarios
        optional_columns = {
            "data_v2": ["NVARCHAR"],  # Only exists in migration scenarios
        }

        for expected_column, expected_type in required_columns.items():
            self.assertIn(
                expected_column,
                table_info,
                f"Expected column '{expected_column}' not found in table '{table_name}'",
            )

            actual_type = table_info[expected_column]
            # Handle both single expected types and lists of acceptable types
            if isinstance(expected_type, list):
                self.assertIn(
                    actual_type.upper(),
                    [t.upper() for t in expected_type],
                    f"Column '{expected_column}' has type '{actual_type}', expected one of {expected_type}",
                )
            else:
                # MSSQL may return different type names, normalize for comparison
                self.assertEqual(
                    actual_type.upper(),
                    expected_type.upper(),
                    f"Column '{expected_column}' has type '{actual_type}', expected '{expected_type}'",
                )

        # Check optional columns if they exist
        for optional_column, expected_type in optional_columns.items():
            if optional_column in table_info:
                actual_type = table_info[optional_column]
                if isinstance(expected_type, list):
                    self.assertIn(
                        actual_type.upper(),
                        [t.upper() for t in expected_type],
                        f"Optional column '{optional_column}' has type '{actual_type}', expected one of {expected_type}",
                    )
                else:
                    self.assertEqual(
                        actual_type.upper(),
                        expected_type.upper(),
                        f"Optional column '{optional_column}' has type '{actual_type}', expected '{expected_type}'",
                    )

    def create_mock_workflow(self) -> Mock:
        """Create a mock workflow object."""
        workflow = Mock()
        workflow.id = "test-workflow-id"
        return workflow

    def create_mock_workflow_log(self) -> Mock:
        """Create a mock workflow log object."""
        return Mock()

    def create_real_connector_instance(self) -> Mock:
        """Create connector instance using real MSSQL connector."""
        connector = Mock()
        connector.connector_id = MSSQL.get_id()
        connector.connector_metadata = self.mssql_config
        # Store reference to real connector for potential future use
        connector._real_mssql_connector = self.mssql_connector
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

    def test_insert_into_db_happy_path_mssql(self) -> None:
        """Test successful insertion into real MSSQL database."""
        # Create mock objects for Django models
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()
        mock_endpoint = self.create_mock_endpoint(mock_connector_instance)

        # Create destination connector with real database connection
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

        # Test the insert_into_db method with real MSSQL
        try:
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
                    # This will execute real database operations using MSSQL connector
                    destination_connector.insert_into_db(
                        input_file_path=self.input_file_path, error=None
                    )

            # Verify the table structure
            self.verify_table_columns(self.test_table_name)

            print("✅ MSSQL integration test completed successfully!")

        except Exception as e:
            print(f"❌ MSSQL integration test failed: {str(e)}")
            raise

    def test_insert_into_db_with_error_mssql(self) -> None:
        """Test insertion with error parameter into real MSSQL database."""
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

        # Verify the table structure
        self.verify_table_columns(self.test_table_name)

        print(
            f"✅ Successfully inserted error data into MSSQL table: {self.test_table_name}"
        )

    def test_mssql_connector_connection(self) -> None:
        """Test that the MSSQL connector can establish a connection."""
        # Test the real MSSQL connector directly
        try:
            engine = self.mssql_connector.get_engine()
            self.assertIsNotNone(engine)
            print("✅ MSSQL connector successfully established connection")

            # Test a simple query to verify connection works
            with engine.cursor() as cursor:
                cursor.execute("SELECT 1 as test_column")
                result = cursor.fetchall()
                self.assertIsNotNone(result)
                print("✅ MSSQL connector successfully executed test query")

            # Clean up
            if hasattr(engine, "close"):
                engine.close()
        except Exception as e:
            self.fail(f"MSSQL connector failed to connect: {str(e)}")

    def tearDown(self) -> None:
        """Clean up test resources."""
        # Optionally clean up test table
        # Note: Be careful with cleanup in production environments
        pass
