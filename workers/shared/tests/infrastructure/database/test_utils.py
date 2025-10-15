import datetime
import json
import unittest

from shared.enums.status_enums import FileProcessingStatus
from shared.infrastructure.database.utils import (
    ColumnModes,
    TableColumns,
    WorkerDatabaseUtils,
)


class TestWorkerDatabaseUtilsFloatSanitization(unittest.TestCase):
    """Test float sanitization integration in WorkerDatabaseUtils."""

    def test_metadata_with_nan_sanitized(self):
        """Test that metadata with NaN values is properly sanitized."""
        metadata = {
            "value": float('nan'),
            "timestamp": 1760509016.282637
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123",
            metadata=metadata
        )
        
        metadata_json = json.loads(values[TableColumns.METADATA])
        self.assertIsNone(metadata_json["value"])
        self.assertEqual(metadata_json["timestamp"], 1760509016.282637)

    def test_metadata_with_infinity_sanitized(self):
        """Test that metadata with infinity values is sanitized."""
        metadata = {
            "pos_inf": float('inf'),
            "neg_inf": float('-inf'),
            "normal": 42.0
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123",
            metadata=metadata
        )
        
        metadata_json = json.loads(values[TableColumns.METADATA])
        self.assertIsNone(metadata_json["pos_inf"])
        self.assertIsNone(metadata_json["neg_inf"])
        self.assertEqual(metadata_json["normal"], 42.0)

    def test_single_column_data_with_nan_sanitized(self):
        """Test that single column data with NaN is sanitized."""
        data = {
            "value": float('nan'),
            "count": 5
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertIsNone(values["data"]["value"])
        self.assertEqual(values["data"]["count"], 5)

    def test_single_column_data_preserves_float_precision(self):
        """Test that single column mode preserves float precision."""
        data = {
            "timestamp": 1760509016.282637123456789,
            "cost": 0.001228
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertEqual(values["data"]["timestamp"], 1760509016.282637123456789)
        self.assertEqual(values["data"]["cost"], 0.001228)

    def test_split_column_data_with_special_floats(self):
        """Test that split column data handles special floats."""
        data = {
            "value": float('inf'),
            "normal": 123.456
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.SPLIT_JSON_INTO_COLUMNS,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertIsNone(values["value"])
        self.assertEqual(values["normal"], 123.456)

    def test_nested_data_structure_sanitization(self):
        """Test sanitization of nested data structures."""
        data = {
            "outer": {
                "inner": {
                    "nan_value": float('nan'),
                    "valid": 42.0
                }
            }
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertIsNone(values["data"]["outer"]["inner"]["nan_value"])
        self.assertEqual(values["data"]["outer"]["inner"]["valid"], 42.0)

    def test_list_data_with_special_floats(self):
        """Test sanitization of list data with special floats."""
        data = [1.23, float('nan'), float('inf'), 4.56]
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        result_list = values["data"]
        self.assertEqual(result_list[0], 1.23)
        self.assertIsNone(result_list[1])
        self.assertIsNone(result_list[2])
        self.assertEqual(result_list[3], 4.56)

    def test_string_data_wrapped_properly(self):
        """Test that string data is wrapped correctly."""
        data = "simple string"
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertEqual(values["data"], {"result": "simple string"})

    def test_none_data_handling(self):
        """Test that None data is handled correctly."""
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=None,
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertNotIn("data", values)

    def test_error_status_set_when_error_provided(self):
        """Test that error status is set correctly."""
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123",
            error="Test error message"
        )
        
        self.assertEqual(values[TableColumns.ERROR_MESSAGE], "Test error message")
        self.assertEqual(values[TableColumns.STATUS], FileProcessingStatus.ERROR)

    def test_success_status_when_no_error(self):
        """Test that success status is set when no error."""
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123"
        )
        
        self.assertEqual(values[TableColumns.STATUS], FileProcessingStatus.SUCCESS)

    def test_agent_name_included_when_requested(self):
        """Test that agent name is included when requested."""
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123",
            include_agent=True,
            agent_name="TEST_AGENT"
        )
        
        self.assertEqual(values[TableColumns.CREATED_BY], "TEST_AGENT")

    def test_timestamp_included_when_requested(self):
        """Test that timestamp is included when requested."""
        before = datetime.datetime.now()
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/test/path",
            execution_id="exec123",
            include_timestamp=True
        )
        after = datetime.datetime.now()
        
        self.assertIn(TableColumns.CREATED_AT, values)
        timestamp = values[TableColumns.CREATED_AT]
        self.assertGreaterEqual(timestamp, before)
        self.assertLessEqual(timestamp, after)

    def test_custom_column_names(self):
        """Test that custom column names work correctly."""
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data={"result": "test"},
            file_path="/custom/path",
            execution_id="custom_id",
            file_path_name="custom_file_path",
            execution_id_name="custom_execution_id",
            single_column_name="custom_data"
        )
        
        self.assertEqual(values["custom_file_path"], "/custom/path")
        self.assertEqual(values["custom_execution_id"], "custom_id")
        self.assertIn("custom_data", values)

    def test_complex_real_world_scenario(self):
        """Test complex real-world data processing scenario."""
        metadata = {
            "execution_time": 1760509016.282637,
            "cpu_usage": 45.67,
            "memory_usage": float('nan'),
            "retry_count": 3
        }
        
        data = {
            "extracted_data": {
                "field1": "value1",
                "field2": 123.456789,
                "field3": float('inf'),
            },
            "confidence_scores": [0.95, 0.87, float('nan'), 0.92]
        }
        
        values = WorkerDatabaseUtils.get_columns_and_values(
            column_mode_str=ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN,
            data=data,
            file_path="/documents/doc1.pdf",
            execution_id="exec-2024-001",
            metadata=metadata,
            include_agent=True,
            include_timestamp=True
        )
        
        metadata_json = json.loads(values[TableColumns.METADATA])
        self.assertIsNone(metadata_json["memory_usage"])
        self.assertEqual(metadata_json["execution_time"], 1760509016.282637)
        
        self.assertIsNone(values["data"]["extracted_data"]["field3"])
        self.assertIsNone(values["data"]["confidence_scores"][2])
        
        self.assertEqual(values["data"]["extracted_data"]["field1"], "value1")
        self.assertEqual(values["file_path"], "/documents/doc1.pdf")


class TestCreateSafeErrorJson(unittest.TestCase):
    """Test safe error JSON creation."""

    def test_creates_error_json_with_details(self):
        """Test that error JSON contains all required details."""
        error = TypeError("Cannot serialize object")
        result = WorkerDatabaseUtils._create_safe_error_json("test_data", error)
        
        self.assertEqual(result["error"], "JSON serialization failed")
        self.assertEqual(result["error_type"], "TypeError")
        self.assertEqual(result["error_message"], "Cannot serialize object")
        self.assertEqual(result["data_description"], "test_data")
        self.assertIn("timestamp", result)


class TestDetermineColumnMode(unittest.TestCase):
    """Test column mode determination."""

    def test_single_column_mode_string(self):
        """Test single column mode string recognition."""
        mode = WorkerDatabaseUtils._determine_column_mode(
            ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN
        )
        self.assertEqual(mode, ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN)

    def test_split_column_mode_string(self):
        """Test split column mode string recognition."""
        mode = WorkerDatabaseUtils._determine_column_mode(
            ColumnModes.SPLIT_JSON_INTO_COLUMNS
        )
        self.assertEqual(mode, ColumnModes.SPLIT_JSON_INTO_COLUMNS)

    def test_invalid_mode_defaults_to_single_column(self):
        """Test that invalid mode defaults to single column."""
        mode = WorkerDatabaseUtils._determine_column_mode("INVALID_MODE")
        self.assertEqual(mode, ColumnModes.WRITE_JSON_TO_A_SINGLE_COLUMN)


class TestHasTableColumn(unittest.TestCase):
    """Test table column existence checking."""

    def test_returns_true_when_column_exists(self):
        """Test returns True when column exists."""
        table_info = {"column1": "STRING", "column2": "INT"}
        result = WorkerDatabaseUtils._has_table_column(table_info, "column1")
        self.assertTrue(result)

    def test_case_insensitive_matching(self):
        """Test that column matching is case-insensitive."""
        table_info = {"Column1": "STRING", "COLUMN2": "INT"}
        result = WorkerDatabaseUtils._has_table_column(table_info, "column1")
        self.assertTrue(result)

    def test_returns_false_when_column_missing(self):
        """Test returns False when column doesn't exist."""
        table_info = {"column1": "STRING"}
        result = WorkerDatabaseUtils._has_table_column(table_info, "column2")
        self.assertFalse(result)

    def test_returns_true_when_table_info_none(self):
        """Test returns True when table_info is None."""
        result = WorkerDatabaseUtils._has_table_column(None, "any_column")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()