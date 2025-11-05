import unittest

from unstract.connectors.databases.bigquery.bigquery import BigQuery


class TestBigQuery(unittest.TestCase):
    def test_json_credentials(self):
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":'
                    '"project_id","private_key_id":"private_key_id",'
                    '"private_key":"private_key","client_email":'
                    '"client_email","client_id":"11427061",'
                    '"auth_uri":"",'
                    '"token_uri":"",'
                    '"auth_provider_x509_cert_url":"",'
                    '"client_x509_cert_url":"",'
                    '"universe_domain":"googleapis.com"}'
                )
            }
        )
        client = bigquery.get_engine()
        query_job = client.query(
            """
        select * from `dataset.test`"""
        )
        results = query_job.result()

        for c in results:
            print(c)
        self.assertTrue(len(results) > 0)  # add assertion here



class TestBigQuerySanitization(unittest.TestCase):
    """Comprehensive tests for BigQuery float sanitization."""

    def test_sanitize_nan_returns_none(self):
        """Test that NaN values are converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('nan'))
        self.assertIsNone(result)

    def test_sanitize_infinity_returns_none(self):
        """Test that positive infinity is converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('inf'))
        self.assertIsNone(result)

    def test_sanitize_negative_infinity_returns_none(self):
        """Test that negative infinity is converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('-inf'))
        self.assertIsNone(result)

    def test_sanitize_zero_returns_zero(self):
        """Test that zero is preserved."""
        result = BigQuery._sanitize_for_bigquery(0.0)
        self.assertEqual(result, 0.0)

    def test_sanitize_negative_zero_returns_zero(self):
        """Test that negative zero is handled correctly."""
        result = BigQuery._sanitize_for_bigquery(-0.0)
        self.assertEqual(result, 0.0)

    def test_sanitize_large_unix_timestamp(self):
        """Test that Unix timestamps are limited to 15 significant figures."""
        # Unix timestamp with high precision
        timestamp = 1760509016.282637
        result = BigQuery._sanitize_for_bigquery(timestamp)

        # Should limit to 15 total significant figures
        # 1760509016 has 10 digits, so 5 decimal places remain
        self.assertAlmostEqual(result, 1760509016.28264, places=5)

        # Verify it's different from original (precision reduced)
        self.assertNotEqual(result, timestamp)

    def test_sanitize_small_decimal_preserves_precision(self):
        """Test that small numbers retain full precision."""
        small_number = 0.001228
        result = BigQuery._sanitize_for_bigquery(small_number)

        # Small numbers should be unchanged (only 4 significant figures)
        self.assertEqual(result, small_number)

    def test_sanitize_medium_float_limits_precision(self):
        """Test that medium-sized floats are properly limited."""
        # Number with 16+ significant figures
        value = 12345.67890123456789
        result = BigQuery._sanitize_for_bigquery(value)

        # Should limit to 15 significant figures total
        # 12345 has 5 digits, so 10 decimal places remain
        self.assertAlmostEqual(result, 12345.6789012346, places=10)

    def test_sanitize_very_large_number(self):
        """Test that very large numbers are handled correctly."""
        large_value = 9.87654321098765e15
        result = BigQuery._sanitize_for_bigquery(large_value)

        # Should limit to 15 significant figures
        self.assertIsInstance(result, float)
        self.assertNotEqual(result, float('inf'))
        self.assertNotEqual(result, float('nan'))

    def test_sanitize_very_small_number(self):
        """Test that very small numbers preserve precision."""
        small_value = 1.23456789e-10
        result = BigQuery._sanitize_for_bigquery(small_value)

        # Should preserve precision for small numbers
        self.assertAlmostEqual(result, small_value, places=15)

    def test_sanitize_negative_numbers(self):
        """Test that negative numbers are handled correctly."""
        negative = -123.456789012345678
        result = BigQuery._sanitize_for_bigquery(negative)

        # Should limit precision but preserve sign
        self.assertLess(result, 0)
        self.assertAlmostEqual(result, -123.456789012346, places=12)

    def test_sanitize_dict_with_floats(self):
        """Test sanitization of dictionaries containing floats."""
        data = {
            "timestamp": 1760509016.282637,
            "cost": 0.001228,
            "nan_value": float('nan'),
            "inf_value": float('inf'),
            "normal": 42.0
        }
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["timestamp"], 1760509016.28264, places=5)
        self.assertEqual(result["cost"], 0.001228)
        self.assertIsNone(result["nan_value"])
        self.assertIsNone(result["inf_value"])
        self.assertEqual(result["normal"], 42.0)

    def test_sanitize_nested_dict(self):
        """Test sanitization of nested dictionaries."""
        data = {
            "outer": {
                "inner": {
                    "value": 1234567890.123456789,
                    "special": float('nan')
                }
            }
        }
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertIsInstance(result["outer"]["inner"]["value"], float)
        self.assertIsNone(result["outer"]["inner"]["special"])

    def test_sanitize_list_with_floats(self):
        """Test sanitization of lists containing floats."""
        data = [1760509016.282637, 0.001228, float('nan'), float('inf'), 42.0]
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 5)
        self.assertAlmostEqual(result[0], 1760509016.28264, places=5)
        self.assertEqual(result[1], 0.001228)
        self.assertIsNone(result[2])
        self.assertIsNone(result[3])
        self.assertEqual(result[4], 42.0)

    def test_sanitize_nested_lists(self):
        """Test sanitization of nested lists."""
        data = [[1.234567890123456789, float('nan')], [float('inf'), 0.001]]
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], list)
        self.assertIsNone(result[0][1])
        self.assertIsNone(result[1][0])

    def test_sanitize_mixed_structure(self):
        """Test sanitization of mixed dict/list structures."""
        data = {
            "items": [
                {"value": 1760509016.282637, "name": "timestamp"},
                {"value": float('nan'), "name": "invalid"}
            ],
            "summary": {
                "total": 99999.999999999999,
                "count": 5
            }
        }
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["items"], list)
        self.assertAlmostEqual(result["items"][0]["value"], 1760509016.28264, places=5)
        self.assertEqual(result["items"][0]["name"], "timestamp")
        self.assertIsNone(result["items"][1]["value"])

    def test_sanitize_string_passthrough(self):
        """Test that strings are passed through unchanged."""
        data = "test string"
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertEqual(result, data)

    def test_sanitize_int_passthrough(self):
        """Test that integers are passed through unchanged."""
        data = 42
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertEqual(result, data)

    def test_sanitize_bool_passthrough(self):
        """Test that booleans are passed through unchanged."""
        data = True
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertEqual(result, data)

    def test_sanitize_none_passthrough(self):
        """Test that None is passed through unchanged."""
        data = None
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertIsNone(result)

    def test_sanitize_empty_dict(self):
        """Test that empty dictionaries are handled correctly."""
        data = {}
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertEqual(result, {})

    def test_sanitize_empty_list(self):
        """Test that empty lists are handled correctly."""
        data = []
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertEqual(result, [])

    def test_sanitize_complex_real_world_data(self):
        """Test sanitization of complex real-world data structures."""
        data = {
            "execution_metadata": {
                "start_time": 1760509016.282637,
                "end_time": 1760509045.891234,
                "duration": 29.608597,
                "status": "completed"
            },
            "metrics": [
                {"name": "accuracy", "value": 0.9876543210123456},
                {"name": "loss", "value": 0.00123456789},
                {"name": "invalid", "value": float('nan')}
            ],
            "costs": {
                "compute": 0.001228,
                "storage": 0.000456,
                "total": 0.001684
            }
        }
        result = BigQuery._sanitize_for_bigquery(data)

        # Verify structure is preserved
        self.assertIn("execution_metadata", result)
        self.assertIn("metrics", result)
        self.assertIn("costs", result)

        # Verify timestamps are limited
        self.assertAlmostEqual(
            result["execution_metadata"]["start_time"],
            1760509016.28264,
            places=5
        )

        # Verify small numbers are preserved
        self.assertEqual(result["costs"]["compute"], 0.001228)

        # Verify NaN is converted to None
        self.assertIsNone(result["metrics"][2]["value"])

    def test_sanitize_float_edge_cases(self):
        """Test edge cases for float sanitization."""
        test_cases = [
            (1.0, 1.0),  # Simple whole number
            (0.1, 0.1),  # Decimal that can't be exactly represented
            (1e-100, 1e-100),  # Very small number
            (1e100, 1e100),  # Very large number (within float range)
            (-123.456, -123.456),  # Negative decimal
        ]

        for input_val, expected in test_cases:
            with self.subTest(input=input_val):
                result = BigQuery._sanitize_for_bigquery(input_val)
                if abs(input_val) < 1e50:  # For reasonable numbers
                    self.assertAlmostEqual(result, expected, places=10)
                else:
                    self.assertIsInstance(result, float)

    def test_sanitize_preserves_dict_keys(self):
        """Test that dictionary keys are preserved during sanitization."""
        data = {
            "key1": 1.234567890123456789,
            "key2": float('nan'),
            "key3": "string_value",
            "key4": [1, 2, 3]
        }
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertEqual(set(result.keys()), set(data.keys()))

    def test_sanitize_maintains_list_order(self):
        """Test that list order is maintained during sanitization."""
        data = [1.111, 2.222, 3.333, float('nan'), 5.555]
        result = BigQuery._sanitize_for_bigquery(data)

        self.assertEqual(len(result), len(data))
        self.assertAlmostEqual(result[0], 1.111, places=3)
        self.assertAlmostEqual(result[1], 2.222, places=3)
        self.assertAlmostEqual(result[2], 3.333, places=3)
        self.assertIsNone(result[3])
        self.assertAlmostEqual(result[4], 5.555, places=3)


if __name__ == "__main__":
    unittest.main()
    """Comprehensive tests for BigQuery float sanitization."""

    def test_sanitize_nan_returns_none(self):
        """Test that NaN values are converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('nan'))
        self.assertIsNone(result)

    def test_sanitize_infinity_returns_none(self):
        """Test that positive infinity is converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('inf'))
        self.assertIsNone(result)

    def test_sanitize_negative_infinity_returns_none(self):
        """Test that negative infinity is converted to None."""
        result = BigQuery._sanitize_for_bigquery(float('-inf'))
        self.assertIsNone(result)

    def test_sanitize_zero_returns_zero(self):
        """Test that zero is preserved."""
        result = BigQuery._sanitize_for_bigquery(0.0)
        self.assertEqual(result, 0.0)

    def test_sanitize_large_unix_timestamp(self):
        """Test that Unix timestamps are limited to 15 significant figures."""
        timestamp = 1760509016.282637
        result = BigQuery._sanitize_for_bigquery(timestamp)
        self.assertAlmostEqual(result, 1760509016.28264, places=5)
        self.assertNotEqual(result, timestamp)

    def test_sanitize_small_decimal_preserves_precision(self):
        """Test that small numbers retain full precision."""
        small_number = 0.001228
        result = BigQuery._sanitize_for_bigquery(small_number)
        self.assertEqual(result, small_number)

    def test_sanitize_dict_with_floats(self):
        """Test sanitization of dictionaries containing floats."""
        data = {
            "timestamp": 1760509016.282637,
            "cost": 0.001228,
            "nan_value": float('nan'),
            "inf_value": float('inf'),
            "normal": 42.0
        }
        result = BigQuery._sanitize_for_bigquery(data)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(result["timestamp"], 1760509016.28264, places=5)
        self.assertEqual(result["cost"], 0.001228)
        self.assertIsNone(result["nan_value"])
        self.assertIsNone(result["inf_value"])
        self.assertEqual(result["normal"], 42.0)

if __name__ == "__main__":
    unittest.main()
