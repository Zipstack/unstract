import os
from unittest.mock import Mock, patch

from django.test import TestCase
from workflow_manager.endpoint_v2.constants import DestinationKey
from workflow_manager.endpoint_v2.destination import DestinationConnector

from unstract.connectors.databases.oracle_db import OracleDB


class TestDestinationConnectorOracle(TestCase):
    """Integration test for insert_into_db method with real Oracle DB connector."""

    def setUp(self) -> None:
        """Set up test data and real Oracle DB configuration."""

        # Oracle DB connection settings for testing
        required_env_vars = [
            "ORACLE_CONFIG_DIR",
            "ORACLE_USER",
            "ORACLE_PASSWORD",
            "ORACLE_DSN",
            "ORACLE_WALLET_LOCATION",
            "ORACLE_WALLET_PASSWORD",
        ]

        # Check if all required environment variables are set
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            self.skipTest(
                f"Required Oracle DB environment variables not set: {', '.join(missing_vars)}"
            )

        self.oracle_config = {
            "config_dir": os.getenv("ORACLE_CONFIG_DIR"),
            "user": os.getenv("ORACLE_USER"),
            "password": os.getenv("ORACLE_PASSWORD"),
            "dsn": os.getenv("ORACLE_DSN"),
            "wallet_location": os.getenv("ORACLE_WALLET_LOCATION"),
            "wallet_password": os.getenv("ORACLE_WALLET_PASSWORD"),
        }

        # Test data that will be inserted into the database
        self.test_data = {"key": "value", "result": "test_result", "status": "success"}
        self.test_metadata = {
            "file_execution_id": "test-file-exec-id",
            "extracted_text": "This is sample extracted text",
            "processing_time": 1.5,
        }
        self.input_file_path = "/path/to/test/file.pdf"

        # Oracle table naming (typically uppercase)
        self.test_table_name = "output_3"

        # Create real Oracle DB connector instance
        self.oracle_connector = OracleDB(settings=self.oracle_config)

        # Expected columns based on configuration (Oracle data types)
        self.expected_columns = {
            "ID": "VARCHAR2",
            "FILE_PATH": "VARCHAR2",
            "EXECUTION_ID": "VARCHAR2",
            "DATA": "CLOB",  # Legacy column remains CLOB after migration
            "DATA_V2": "CLOB",  # New CLOB column added during migration
            "METADATA": "CLOB",  # New CLOB column added during migration
            "CREATED_AT": "TIMESTAMP",
            "CREATED_BY": "VARCHAR2",
            "STATUS": "VARCHAR2",
            "ERROR_MESSAGE": "VARCHAR2",
            "USER_FIELD_1": "NUMBER",
            "USER_FIELD_2": "NUMBER",
            "USER_FIELD_3": "VARCHAR2",
        }

    def verify_table_columns(self, table_name: str) -> None:
        """Verify that the table has expected columns with correct data types."""
        table_info = self.oracle_connector.get_information_schema(table_name=table_name)

        print(f"🔍 Actual table structure for '{table_name}': {table_info}")

        # Check that key columns exist (some columns may be created on-demand)
        required_columns = {
            "ID": ["VARCHAR2"],  # Oracle uses VARCHAR2
            "FILE_PATH": ["CLOB", "VARCHAR2"],  # Oracle can use either CLOB or VARCHAR2
            "EXECUTION_ID": [
                "CLOB",
                "VARCHAR2",
            ],  # Oracle can use either CLOB or VARCHAR2
            "DATA": [
                "CLOB",
                "VARCHAR2",
            ],  # Can be CLOB or VARCHAR2, depends on migration scenario
            "METADATA": [
                "CLOB",
            ],  # New CLOB column added during migration for JSON data
            "CREATED_AT": ["TIMESTAMP", "TIMESTAMP(6)"],  # Oracle timestamp types
            "CREATED_BY": ["VARCHAR2"],  # Oracle uses VARCHAR2
        }

        # Optional columns that may exist in migration scenarios
        optional_columns = {
            "DATA_V2": [
                "CLOB",
                "VARCHAR2",
            ],  # Can be CLOB or VARCHAR2 in migration scenarios
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
                # Oracle may return different type names, normalize for comparison
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
        """Create connector instance using real Oracle DB connector."""
        connector = Mock()
        connector.connector_id = OracleDB.get_id()
        connector.connector_metadata = self.oracle_config
        # Store reference to real connector for potential future use
        connector._real_oracle_connector = self.oracle_connector
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

    def test_insert_into_db_happy_path_oracle(self) -> None:
        """Test successful insertion into real Oracle DB database."""
        # Create mock objects for Django models
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()
        mock_endpoint = self.create_mock_endpoint(mock_connector_instance)

        # Create destination connector with real database connection
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

        # Test the insert_into_db method with real Oracle DB
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
                    # This will execute real database operations using Oracle DB connector
                    destination_connector.insert_into_db(
                        input_file_path=self.input_file_path, error=None
                    )

            # Verify the table structure
            self.verify_table_columns(self.test_table_name)

            print("✅ Oracle DB integration test completed successfully!")

        except Exception as e:
            print(f"❌ Oracle DB integration test failed: {str(e)}")
            raise

    def test_insert_into_db_with_error_oracle(self) -> None:
        """Test insertion with error parameter into real Oracle DB database."""
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
            f"✅ Successfully inserted error data into Oracle DB table: {self.test_table_name}"
        )

    def test_oracle_connector_connection(self) -> None:
        """Test that the Oracle DB connector can establish a connection."""
        # Test the real Oracle DB connector directly
        try:
            engine = self.oracle_connector.get_engine()
            self.assertIsNotNone(engine)
            print("✅ Oracle DB connector successfully established connection")

            # Test a simple query to verify connection works
            with engine.cursor() as cursor:
                cursor.execute("SELECT 1 as test_column FROM DUAL")
                result = cursor.fetchall()
                self.assertIsNotNone(result)
                print("✅ Oracle DB connector successfully executed test query")

            # Clean up
            if hasattr(engine, "close"):
                engine.close()
        except Exception as e:
            self.fail(f"Oracle DB connector failed to connect: {str(e)}")

    def tearDown(self) -> None:
        """Clean up test resources."""
        # Optionally clean up test table
        # Note: Be careful with cleanup in production environments
        pass
