import unittest

from unstract.connectors.databases.utils import sanitize_floats_for_database


class TestSanitizeFloatsForDatabase(unittest.TestCase):
    """Comprehensive tests for database float sanitization utility."""

    def test_nan_converted_to_none(self):
        """Test that NaN values are converted to None."""
        result = sanitize_floats_for_database(float('nan'))
        self.assertIsNone(result)

    def test_positive_infinity_converted_to_none(self):
        """Test that positive infinity is converted to None."""
        result = sanitize_floats_for_database(float('inf'))
        self.assertIsNone(result)

    def test_negative_infinity_converted_to_none(self):
        """Test that negative infinity is converted to None."""
        result = sanitize_floats_for_database(float('-inf'))
        self.assertIsNone(result)

    def test_normal_float_unchanged(self):
        """Test that normal floats are not modified."""
        test_value = 1760509016.282637
        result = sanitize_floats_for_database(test_value)
        self.assertEqual(result, test_value)

    def test_zero_unchanged(self):
        """Test that zero is preserved."""
        result = sanitize_floats_for_database(0.0)
        self.assertEqual(result, 0.0)

    def test_negative_float_unchanged(self):
        """Test that negative floats are preserved."""
        test_value = -123.456789
        result = sanitize_floats_for_database(test_value)
        self.assertEqual(result, test_value)

    def test_small_float_unchanged(self):
        """Test that small floats retain full precision."""
        test_value = 0.001228
        result = sanitize_floats_for_database(test_value)
        self.assertEqual(result, test_value)

    def test_large_float_unchanged(self):
        """Test that large floats retain full precision."""
        test_value = 9876543210.123456789
        result = sanitize_floats_for_database(test_value)
        self.assertEqual(result, test_value)

    def test_dict_with_nan(self):
        """Test sanitization of dictionary with NaN values."""
        data = {
            "valid": 42.5,
            "invalid": float('nan'),
            "name": "test"
        }
        result = sanitize_floats_for_database(data)
        
        self.assertEqual(result["valid"], 42.5)
        self.assertIsNone(result["invalid"])
        self.assertEqual(result["name"], "test")

    def test_dict_with_infinity(self):
        """Test sanitization of dictionary with infinity values."""
        data = {
            "pos_inf": float('inf'),
            "neg_inf": float('-inf'),
            "normal": 123.456
        }
        result = sanitize_floats_for_database(data)
        
        self.assertIsNone(result["pos_inf"])
        self.assertIsNone(result["neg_inf"])
        self.assertEqual(result["normal"], 123.456)

    def test_nested_dict(self):
        """Test sanitization of nested dictionaries."""
        data = {
            "level1": {
                "level2": {
                    "valid": 1.23,
                    "invalid": float('nan')
                },
                "inf": float('inf')
            }
        }
        result = sanitize_floats_for_database(data)
        
        self.assertEqual(result["level1"]["level2"]["valid"], 1.23)
        self.assertIsNone(result["level1"]["level2"]["invalid"])
        self.assertIsNone(result["level1"]["inf"])

    def test_list_with_special_floats(self):
        """Test sanitization of list with special float values."""
        data = [1.23, float('nan'), 4.56, float('inf'), float('-inf')]
        result = sanitize_floats_for_database(data)
        
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], 1.23)
        self.assertIsNone(result[1])
        self.assertEqual(result[2], 4.56)
        self.assertIsNone(result[3])
        self.assertIsNone(result[4])

    def test_nested_list(self):
        """Test sanitization of nested lists."""
        data = [
            [1.23, float('nan')],
            [float('inf'), 4.56]
        ]
        result = sanitize_floats_for_database(data)
        
        self.assertEqual(result[0][0], 1.23)
        self.assertIsNone(result[0][1])
        self.assertIsNone(result[1][0])
        self.assertEqual(result[1][1], 4.56)

    def test_mixed_dict_and_list(self):
        """Test sanitization of mixed dict/list structures."""
        data = {
            "items": [
                {"value": 1.23, "valid": True},
                {"value": float('nan'), "valid": False}
            ],
            "summary": {
                "total": 100.0,
                "invalid": float('inf')
            }
        }
        result = sanitize_floats_for_database(data)
        
        self.assertEqual(result["items"][0]["value"], 1.23)
        self.assertIsNone(result["items"][1]["value"])
        self.assertEqual(result["summary"]["total"], 100.0)
        self.assertIsNone(result["summary"]["invalid"])

    def test_string_passthrough(self):
        """Test that strings pass through unchanged."""
        data = "test string"
        result = sanitize_floats_for_database(data)
        self.assertEqual(result, data)

    def test_int_passthrough(self):
        """Test that integers pass through unchanged."""
        data = 42
        result = sanitize_floats_for_database(data)
        self.assertEqual(result, data)

    def test_bool_passthrough(self):
        """Test that booleans pass through unchanged."""
        data = True
        result = sanitize_floats_for_database(data)
        self.assertTrue(result)

    def test_none_passthrough(self):
        """Test that None passes through unchanged."""
        data = None
        result = sanitize_floats_for_database(data)
        self.assertIsNone(result)

    def test_empty_dict(self):
        """Test that empty dictionaries are handled."""
        data = {}
        result = sanitize_floats_for_database(data)
        self.assertEqual(result, {})

    def test_empty_list(self):
        """Test that empty lists are handled."""
        data = []
        result = sanitize_floats_for_database(data)
        self.assertEqual(result, [])

    def test_precision_not_modified(self):
        """Test that float precision is not modified."""
        timestamp = 1760509016.282637123456789
        result = sanitize_floats_for_database(timestamp)
        self.assertEqual(result, timestamp)

    def test_complex_real_world_metadata(self):
        """Test sanitization of complex real-world metadata."""
        metadata = {
            "execution": {
                "start_time": 1760509016.282637,
                "end_time": 1760509045.891234,
                "duration": 29.608597
            },
            "metrics": {
                "success_rate": 0.987654321,
                "error_rate": float('nan'),
                "timeout_rate": 0.001234
            },
            "resources": {
                "cpu_usage": 45.67,
                "memory_usage": float('inf'),
                "disk_usage": 123.456789
            }
        }
        result = sanitize_floats_for_database(metadata)
        
        self.assertEqual(result["execution"]["start_time"], 1760509016.282637)
        self.assertEqual(result["metrics"]["success_rate"], 0.987654321)
        self.assertIsNone(result["metrics"]["error_rate"])
        self.assertIsNone(result["resources"]["memory_usage"])


if __name__ == "__main__":
    unittest.main()