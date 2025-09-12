import json
import os
from unittest.mock import Mock, patch

from django.test import TestCase
from workflow_manager.endpoint_v2.constants import DestinationKey
from workflow_manager.endpoint_v2.destination import DestinationConnector

from unstract.connectors.databases.mariadb import MariaDB


class TestDestinationConnectorMariaDB(TestCase):
    """Integration test for insert_into_db method with real MariaDB connector."""

    def setUp(self) -> None:
        """Set up test data and real MariaDB configuration."""

        # MariaDB connection settings for testing
        required_env_vars = [
            "MARIADB_HOST",
            "MARIADB_PORT",
            "MARIADB_DATABASE",
            "MARIADB_USER",
            "MARIADB_PASSWORD",
        ]

        # Check if all required environment variables are set
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            self.skipTest(
                f"Required MariaDB environment variables not set: {', '.join(missing_vars)}"
            )

        self.mariadb_config = {
            "host": os.getenv("MARIADB_HOST"),
            "port": os.getenv("MARIADB_PORT"),
            "database": os.getenv("MARIADB_DATABASE"),
            "user": os.getenv("MARIADB_USER"),
            "password": os.getenv("MARIADB_PASSWORD"),
        }

        # Test data that will be inserted into the database
        self.test_data = {"key": "value", "result": "test_result", "status": "success"}
        self.test_metadata = {
            "file_execution_id": "test-file-exec-id",
            "extracted_text": "This is sample extracted text",
            "processing_time": 1.5,
        }
        self.input_file_path = "/path/to/test/file.pdf"
        self.test_table_name = "MIGRATION"

        # Create real MariaDB connector instance
        self.mariadb_connector = MariaDB(settings=self.mariadb_config)

        # Expected columns based on configuration (MariaDB/MySQL data types)
        self.expected_columns = {
            "id": "longtext",
            "file_path": "longtext",
            "execution_id": "longtext",
            "data": "longtext",
            "created_at": "timestamp",
            "created_by": "longtext",
            "metadata": "json",
            "error_message": "longtext",
            "status": "enum",
            "user_field_1": "tinyint",  # BOOLEAN maps to TINYINT in MariaDB
            "user_field_2": "bigint",
            "user_field_3": "longtext",
        }

    def verify_table_columns(self, table_name: str) -> None:
        """Verify that all expected columns exist in the table with correct types."""
        table_info = self.mariadb_connector.get_information_schema(
            table_name=table_name
        )

        print(f"🔍 Actual table structure for '{table_name}': {table_info}")

        # Check that key columns exist (some columns may be created on-demand)
        required_columns = {
            "id": "longtext",
            "file_path": "longtext",
            "execution_id": "longtext",
            "data": "longtext",
            "created_at": "timestamp",
            "created_by": "longtext",
        }

        for expected_column, expected_type in required_columns.items():
            self.assertIn(
                expected_column,
                table_info,
                f"Expected column '{expected_column}' not found in table '{table_name}'",
            )

            actual_type = table_info[expected_column].lower()
            expected_type_lower = expected_type.lower()

            # MariaDB may return slightly different type names, so we do flexible matching
            if expected_type_lower == "timestamp":
                self.assertIn(
                    actual_type,
                    ["timestamp", "datetime", "timestamp(0)"],
                    f"Column '{expected_column}' has type '{actual_type}', expected timestamp-like type",
                )
            elif expected_type_lower == "tinyint":
                self.assertIn(
                    actual_type,
                    ["tinyint", "tinyint(1)", "boolean", "bool"],
                    f"Column '{expected_column}' has type '{actual_type}', expected boolean/tinyint type",
                )
            else:
                self.assertEqual(
                    actual_type,
                    expected_type_lower,
                    f"Column '{expected_column}' has type '{actual_type}', expected '{expected_type_lower}'",
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
        """Create connector instance using real MariaDB connector."""
        connector = Mock()
        connector.connector_id = MariaDB.get_id()
        connector.connector_metadata = self.mariadb_config
        # Store reference to real connector for potential future use
        connector._real_mariadb_connector = self.mariadb_connector
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

    def test_insert_into_db_happy_path_mariadb(self) -> None:
        """Test successful insertion into real MariaDB database."""
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
                # This will execute real database operations using MariaDB connector
                destination_connector.insert_into_db(
                    input_file_path=self.input_file_path, error=None
                )

        # Verify that all expected columns were created
        self.verify_table_columns(self.test_table_name)

        print(
            f"✅ Successfully inserted test data into MariaDB table: {self.test_table_name}"
        )

    def test_insert_into_db_with_error_mariadb(self) -> None:
        """Test insertion with error parameter into real MariaDB database."""
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
            f"✅ Successfully inserted error data into MariaDB table: {self.test_table_name}"
        )

    def test_mariadb_connector_connection(self) -> None:
        """Test that the MariaDB connector can establish a connection."""
        # Test the real MariaDB connector directly
        try:
            engine = self.mariadb_connector.get_engine()
            self.assertIsNotNone(engine)
            print("✅ MariaDB connector successfully established connection")

            # Test a simple query to verify connection works
            cursor = engine.cursor()
            cursor.execute("SELECT 1 as test_column")
            result = cursor.fetchall()
            self.assertIsNotNone(result)
            self.assertEqual(result[0][0], 1)
            cursor.close()
            print("✅ MariaDB connector successfully executed test query")

            # Clean up
            if hasattr(engine, "close"):
                engine.close()
        except Exception as e:
            self.fail(f"MariaDB connector failed to connect: {str(e)}")

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
        engine = self.mariadb_connector.get_engine()
        try:
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

    def test_mariadb_specific_data_types(self) -> None:
        """Test MariaDB-specific data types and constraints."""
        # Test that status column accepts ENUM values correctly
        engine = self.mariadb_connector.get_engine()
        try:
            cursor = engine.cursor()

            # Create the table first if it doesn't exist
            create_table_query = self.mariadb_connector.get_create_table_base_query(
                self.test_table_name
            )
            # Add the required columns for the test
            create_table_query += (
                "file_path LONGTEXT, " "execution_id LONGTEXT, " "data LONGTEXT)"
            )

            cursor.execute(create_table_query)

            # Test inserting valid ENUM values
            cursor.execute(
                f"INSERT INTO {self.test_table_name} (id, status, created_at) VALUES (%s, %s, NOW())",
                ("test-enum-1", "SUCCESS"),
            )

            cursor.execute(
                f"INSERT INTO {self.test_table_name} (id, status, created_at) VALUES (%s, %s, NOW())",
                ("test-enum-2", "ERROR"),
            )

            # Verify the data was inserted
            cursor.execute(
                f"SELECT id, status FROM {self.test_table_name} WHERE id IN (%s, %s)",
                ("test-enum-1", "test-enum-2"),
            )
            results = cursor.fetchall()

            self.assertEqual(len(results), 2, "Expected 2 rows to be inserted")

            # Verify ENUM values
            statuses = [row[1] for row in results]
            self.assertIn("SUCCESS", statuses)
            self.assertIn("ERROR", statuses)

            cursor.close()
            print("✅ MariaDB ENUM data type verification successful")

        finally:
            if hasattr(engine, "close"):
                engine.close()

    def test_mariadb_legacy_to_v2_migration(self) -> None:
        """Test complete legacy table to v2 migration workflow."""
        legacy_table_name = "output_1"

        # # Step 1: Create a legacy table manually (simulating old table structure)
        # print("🏗️ Step 1: Creating legacy table...")
        # self._create_legacy_table(legacy_table_name)

        # Step 2: Verify table is detected as legacy
        print("🔍 Step 2: Verifying table is detected as legacy...")
        is_legacy = self._verify_table_is_legacy(legacy_table_name)
        self.assertTrue(is_legacy, "Table should be detected as legacy")

        # Step 3: Trigger migration using the real migration flow
        print("⚡ Step 3: Initiating migration...")
        self._initiate_migration_via_workflow(legacy_table_name)

        # Step 4: Verify migration was successful
        print("✅ Step 4: Verifying migration success...")
        self._verify_migration_success(legacy_table_name)

        # Step 5: Test dual column writing (legacy + v2)
        print("📝 Step 5: Testing dual column writing...")
        self._test_dual_column_writing(legacy_table_name)

        print("🎉 Migration test completed successfully!")

    def _create_legacy_table(self, table_name: str) -> None:
        """Create a legacy table structure (data column as LONGTEXT, not JSON)."""
        engine = self.mariadb_connector.get_engine()
        try:
            cursor = engine.cursor()

            # FORCE DROP AND RECREATE to ensure clean legacy table
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            print(f"🗑️ Dropped existing table '{table_name}' if it existed")

            # Create fresh legacy table with LONGTEXT data column (not JSON)
            legacy_create_query = f"""
            CREATE TABLE {table_name} (
                id LONGTEXT,
                created_by LONGTEXT,
                created_at TIMESTAMP,
                data LONGTEXT,
                file_path LONGTEXT,
                execution_id LONGTEXT
            )
            """

            cursor.execute(legacy_create_query)
            print(
                f"📋 Created fresh legacy table '{table_name}' with LONGTEXT data column"
            )

            # Insert some legacy data to make it realistic
            cursor.execute(
                f"INSERT INTO {table_name} (id, created_by, created_at, data, file_path, execution_id) VALUES (%s, %s, NOW(), %s, %s, %s)",
                (
                    "legacy-1",
                    "Legacy/DBWriter",
                    '{"old": "legacy_data"}',
                    "/legacy/file.pdf",
                    "legacy-exec-1",
                ),
            )
            print(f"📝 Inserted legacy test data into '{table_name}'")

            cursor.close()
            print(f"✅ Legacy table '{table_name}' setup completed")

        finally:
            if hasattr(engine, "close"):
                engine.close()

    def _verify_table_is_legacy(self, table_name: str) -> bool:
        """Verify that table is detected as legacy using the real detection logic."""
        try:
            # Use the actual detection logic from the codebase
            is_string_column = self.mariadb_connector.is_string_column(
                table_info=self.mariadb_connector.get_information_schema(table_name),
                column_name="data",
            )

            if is_string_column:
                print(
                    f"✅ Table '{table_name}' correctly detected as legacy (data column is string type)"
                )
                return True
            else:
                print(f"❌ Table '{table_name}' not detected as legacy")
                return False

        except Exception as e:
            print(f"❌ Error checking legacy status: {e}")
            return False

    def _initiate_migration_via_workflow(self, table_name: str) -> None:
        """Initiate migration using the real workflow destination connector logic."""
        # Create mock objects for the workflow system
        mock_workflow = self.create_mock_workflow()
        mock_workflow_log = self.create_mock_workflow_log()
        mock_connector_instance = self.create_real_connector_instance()

        # Create endpoint with the legacy table name
        mock_endpoint = Mock()
        mock_endpoint.connector_instance = mock_connector_instance
        mock_endpoint.configuration = {
            DestinationKey.TABLE: table_name,  # Use legacy table
            DestinationKey.INCLUDE_AGENT: True,
            DestinationKey.INCLUDE_TIMESTAMP: True,
            DestinationKey.AGENT_NAME: "Unstract/DBWriter",
            DestinationKey.COLUMN_MODE: "Write JSON to a single column",
            DestinationKey.SINGLE_COLUMN_NAME: "data",
            DestinationKey.FILE_PATH: "file_path",
            DestinationKey.EXECUTION_ID: "execution_id",
        }

        # Create destination connector
        destination_connector = self.create_destination_connector(
            mock_workflow, mock_workflow_log, mock_endpoint
        )

        # Mock the data methods to provide test data
        test_migration_data = {"migration_test": "v2_data", "status": "migrated"}
        test_migration_metadata = {
            "file_execution_id": "migration-test-exec-id",
            "migration_test": True,
            "extracted_text": "Migration test extracted text",
        }

        with patch.object(
            destination_connector,
            "get_tool_execution_result",
            return_value=test_migration_data,
        ):
            with patch.object(
                destination_connector,
                "get_combined_metadata",
                return_value=test_migration_metadata,
            ):
                # This should trigger the migration logic automatically
                destination_connector.insert_into_db(
                    input_file_path="/migration/test/file.pdf", error=None
                )

        print(f"✅ Migration initiated for table '{table_name}'")

    def _verify_migration_success(self, table_name: str) -> None:
        """Verify that migration was successful by checking for v2 columns."""
        table_info = self.mariadb_connector.get_information_schema(table_name)

        # Check for v2 columns that should have been added during migration
        expected_v2_columns = {
            "data_v2": "json",
            "metadata": "json",
            "user_field_1": "tinyint",
            "user_field_2": "bigint",
            "user_field_3": "longtext",
            "status": "enum",
            "error_message": "longtext",
        }

        for column_name, expected_type in expected_v2_columns.items():
            self.assertIn(
                column_name,
                table_info,
                f"Migration failed: Column '{column_name}' not found after migration",
            )

            actual_type = table_info[column_name].lower()
            if expected_type == "json":
                # MariaDB might return different representations for JSON
                self.assertIn(
                    actual_type,
                    ["json", "longtext"],  # MariaDB sometimes shows JSON as longtext
                    f"Column '{column_name}' has type '{actual_type}', expected JSON-compatible type",
                )
            elif expected_type == "enum":
                self.assertIn(
                    actual_type,
                    ["enum"],
                    f"Column '{column_name}' has type '{actual_type}', expected enum type",
                )
            else:
                self.assertEqual(
                    actual_type,
                    expected_type,
                    f"Column '{column_name}' has type '{actual_type}', expected '{expected_type}'",
                )

        print(
            f"✅ Migration verification successful - all v2 columns present in '{table_name}'"
        )

    def _test_dual_column_writing(self, table_name: str) -> None:
        """Test that data is written to both legacy and v2 columns after migration."""
        engine = self.mariadb_connector.get_engine()
        try:
            cursor = engine.cursor()

            # Query the latest inserted row to verify dual writing
            cursor.execute(
                f"""
                SELECT data, data_v2, metadata, status, error_message
                FROM {table_name}
                WHERE file_path = '/migration/test/file.pdf'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()

            self.assertIsNotNone(row, "No migrated data found in table")

            data_legacy, data_v2, metadata, status, error_message = row

            # Verify legacy column has data
            self.assertIsNotNone(data_legacy, "Legacy data column should not be empty")

            # Verify v2 column has data
            self.assertIsNotNone(data_v2, "V2 data column should not be empty")

            # Verify metadata column has data
            self.assertIsNotNone(metadata, "Metadata column should not be empty")

            # Verify status is set correctly
            self.assertEqual(
                status, "SUCCESS", "Status should be SUCCESS for successful migration"
            )

            # Parse and verify JSON data (if stored as JSON string in legacy)
            if isinstance(data_legacy, str):
                try:
                    parsed_legacy = json.loads(data_legacy)
                    self.assertIn(
                        "migration_test",
                        parsed_legacy,
                        "Legacy data should contain migration test data",
                    )
                except json.JSONDecodeError:
                    # If not JSON, just verify it contains our test data somehow
                    self.assertIn("migration_test", str(data_legacy))

            cursor.close()
            print(f"✅ Dual column writing verification successful for '{table_name}'")

        finally:
            if hasattr(engine, "close"):
                engine.close()

    def tearDown(self) -> None:
        """Clean up test resources."""
        # Optionally clean up test tables
        # Note: Be careful with cleanup in production environments
        # TEMPORARILY DISABLED FOR DEBUGGING - Uncomment to clean up tables
        # try:
        #     engine = self.mariadb_connector.get_engine()
        #     cursor = engine.cursor()
        #     # Clean up both regular test table and migration test table
        #     cursor.execute(f"DROP TABLE IF EXISTS {self.test_table_name}")
        #     cursor.execute(f"DROP TABLE IF EXISTS LEGACY_OUTPUT_TEST")
        #     cursor.close()
        #     engine.close()
        # except Exception:
        #     # Ignore cleanup errors
        pass
