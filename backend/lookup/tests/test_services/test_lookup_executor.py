"""
Tests for Look-Up Executor implementation.

This module tests the LookUpExecutor class including execution flow,
caching, error handling, and response parsing.
"""

import json
import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest

from lookup.exceptions import (
    ExtractionNotCompleteError,
    ParseError,
)
from lookup.services.lookup_executor import LookUpExecutor


class TestLookUpExecutor:
    """Test cases for LookUpExecutor class."""

    @pytest.fixture
    def mock_variable_resolver(self):
        """Create a mock VariableResolver class."""
        mock_class = Mock()
        mock_instance = Mock()
        mock_instance.resolve.return_value = "Resolved prompt text"
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def mock_cache(self):
        """Create a mock LLMResponseCache."""
        cache = MagicMock()
        cache.generate_cache_key.return_value = "cache_key_123"
        cache.get.return_value = None  # Default to cache miss
        return cache

    @pytest.fixture
    def mock_ref_loader(self):
        """Create a mock ReferenceDataLoader."""
        loader = MagicMock()
        loader.load_latest_for_project.return_value = {
            'version': 1,
            'content': "Reference data content",
            'files': [],
            'total_size': 1000
        }
        return loader

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = MagicMock()
        client.generate.return_value = '{"canonical_vendor": "Slack", "confidence": 0.92}'
        return client

    @pytest.fixture
    def mock_project(self):
        """Create a mock LookupProject."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "Test Look-Up"
        project.llm_config = {'temperature': 0.7}

        # Create mock template
        template = MagicMock()
        template.template_text = "Match {{input_data.vendor}} with {{reference_data}}"
        project.template = template

        return project

    @pytest.fixture
    def executor(self, mock_variable_resolver, mock_cache, mock_ref_loader, mock_llm_client):
        """Create a LookUpExecutor instance with mocked dependencies."""
        return LookUpExecutor(
            variable_resolver=mock_variable_resolver,
            cache_manager=mock_cache,
            reference_loader=mock_ref_loader,
            llm_client=mock_llm_client
        )

    @pytest.fixture
    def sample_input_data(self):
        """Create sample input data."""
        return {
            'vendor': 'Slack India Pvt Ltd',
            'invoice_amount': 5000
        }

    # ========== Successful Execution Tests ==========

    def test_successful_execution(self, executor, mock_project, sample_input_data,
                                 mock_variable_resolver, mock_cache, mock_llm_client):
        """Test complete successful execution flow."""
        result = executor.execute(mock_project, sample_input_data)

        # Check success
        assert result['status'] == 'success'
        assert result['project_id'] == mock_project.id
        assert result['project_name'] == 'Test Look-Up'

        # Check enrichment data
        assert result['data'] == {'canonical_vendor': 'Slack'}
        assert result['confidence'] == 0.92
        assert result['cached'] is False
        assert result['execution_time_ms'] > 0

        # Verify variable resolver was called
        mock_variable_resolver.assert_called_once_with(
            sample_input_data, "Reference data content"
        )
        mock_variable_resolver.return_value.resolve.assert_called_once_with(
            "Match {{input_data.vendor}} with {{reference_data}}"
        )

        # Verify cache was checked and set
        mock_cache.get.assert_called_once_with("cache_key_123")
        mock_cache.set.assert_called_once_with(
            "cache_key_123",
            '{"canonical_vendor": "Slack", "confidence": 0.92}'
        )

        # Verify LLM was called
        mock_llm_client.generate.assert_called_once_with(
            "Resolved prompt text",
            {'temperature': 0.7}
        )

    def test_confidence_extraction(self, executor, mock_project, sample_input_data,
                                  mock_llm_client):
        """Test confidence score extraction from response."""
        mock_llm_client.generate.return_value = '{"field": "value", "confidence": 0.85}'

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'success'
        assert result['confidence'] == 0.85
        assert result['data'] == {'field': 'value'}

    def test_no_confidence_in_response(self, executor, mock_project, sample_input_data,
                                      mock_llm_client):
        """Test handling response without confidence score."""
        mock_llm_client.generate.return_value = '{"field": "value"}'

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'success'
        assert result['confidence'] is None
        assert result['data'] == {'field': 'value'}

    # ========== Cache Tests ==========

    def test_cache_hit(self, executor, mock_project, sample_input_data,
                       mock_cache, mock_llm_client):
        """Test execution with cache hit."""
        # Set up cache hit
        mock_cache.get.return_value = '{"cached_field": "cached_value", "confidence": 0.88}'

        result = executor.execute(mock_project, sample_input_data)

        # Check result
        assert result['status'] == 'success'
        assert result['data'] == {'cached_field': 'cached_value'}
        assert result['confidence'] == 0.88
        assert result['cached'] is True
        assert result['execution_time_ms'] == 0

        # Verify LLM was NOT called
        mock_llm_client.generate.assert_not_called()

        # Verify cache.set was NOT called
        mock_cache.set.assert_not_called()

    def test_cache_miss(self, executor, mock_project, sample_input_data,
                       mock_cache, mock_llm_client):
        """Test execution with cache miss."""
        # Cache miss (default setup)
        mock_cache.get.return_value = None

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'success'
        assert result['cached'] is False

        # Verify LLM was called
        mock_llm_client.generate.assert_called_once()

        # Verify result was cached
        mock_cache.set.assert_called_once()

    # ========== Error Handling Tests ==========

    def test_reference_data_not_ready(self, executor, mock_project, sample_input_data,
                                     mock_ref_loader):
        """Test handling of incomplete extraction."""
        mock_ref_loader.load_latest_for_project.side_effect = ExtractionNotCompleteError(
            ['file1.csv', 'file2.txt']
        )

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Reference data extraction not complete' in result['error']
        assert 'file1.csv' in result['error']
        assert 'file2.txt' in result['error']

    def test_missing_template(self, executor, mock_project, sample_input_data):
        """Test handling of missing template."""
        mock_project.template = None

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Missing prompt template' in result['error']

    def test_llm_timeout(self, executor, mock_project, sample_input_data, mock_llm_client):
        """Test handling of LLM timeout."""
        mock_llm_client.generate.side_effect = TimeoutError("Request timed out after 30s")

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'LLM request timed out' in result['error']
        assert '30s' in result['error']

    def test_llm_generic_error(self, executor, mock_project, sample_input_data,
                              mock_llm_client):
        """Test handling of generic LLM errors."""
        mock_llm_client.generate.side_effect = Exception("API key invalid")

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'LLM request failed' in result['error']
        assert 'API key invalid' in result['error']

    def test_parse_error_invalid_json(self, executor, mock_project, sample_input_data,
                                     mock_llm_client):
        """Test handling of invalid JSON response."""
        mock_llm_client.generate.return_value = "Not valid JSON"

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Failed to parse LLM response' in result['error']

    def test_parse_error_not_object(self, executor, mock_project, sample_input_data,
                                   mock_llm_client):
        """Test handling of non-object JSON response."""
        mock_llm_client.generate.return_value = '["array", "not", "object"]'

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Failed to parse LLM response' in result['error']

    def test_reference_loader_error(self, executor, mock_project, sample_input_data,
                                   mock_ref_loader):
        """Test handling of reference loader errors."""
        mock_ref_loader.load_latest_for_project.side_effect = Exception("Storage unavailable")

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Failed to load reference data' in result['error']
        assert 'Storage unavailable' in result['error']

    # ========== Variable Resolution Tests ==========

    def test_variable_resolution(self, executor, mock_project, sample_input_data,
                                mock_variable_resolver):
        """Test that variables are correctly resolved."""
        result = executor.execute(mock_project, sample_input_data)

        # Verify resolver was instantiated with correct data
        mock_variable_resolver.assert_called_once_with(
            sample_input_data,
            "Reference data content"
        )

        # Verify resolve was called with template
        mock_variable_resolver.return_value.resolve.assert_called_once_with(
            "Match {{input_data.vendor}} with {{reference_data}}"
        )

    # ========== Response Parsing Tests ==========

    def test_parse_llm_response_with_confidence(self, executor):
        """Test parsing response with confidence score."""
        response = '{"field1": "value1", "field2": "value2", "confidence": 0.95}'

        data, confidence = executor._parse_llm_response(response)

        assert data == {'field1': 'value1', 'field2': 'value2'}
        assert confidence == 0.95

    def test_parse_llm_response_without_confidence(self, executor):
        """Test parsing response without confidence score."""
        response = '{"field1": "value1", "field2": "value2"}'

        data, confidence = executor._parse_llm_response(response)

        assert data == {'field1': 'value1', 'field2': 'value2'}
        assert confidence is None

    def test_parse_llm_response_invalid_confidence(self, executor):
        """Test handling of invalid confidence values."""
        # Confidence outside range (should be clamped)
        response = '{"field": "value", "confidence": 1.5}'

        with patch('lookup.services.lookup_executor.logger') as mock_logger:
            data, confidence = executor._parse_llm_response(response)

            assert data == {'field': 'value'}
            assert confidence == 1.0  # Clamped to max
            mock_logger.warning.assert_called()

    def test_parse_llm_response_non_numeric_confidence(self, executor):
        """Test handling of non-numeric confidence."""
        response = '{"field": "value", "confidence": "high"}'

        with patch('lookup.services.lookup_executor.logger') as mock_logger:
            data, confidence = executor._parse_llm_response(response)

            assert data == {'field': 'value'}
            assert confidence is None
            mock_logger.warning.assert_called()

    def test_parse_llm_response_invalid_json(self, executor):
        """Test parsing invalid JSON raises ParseError."""
        response = "This is not JSON"

        with pytest.raises(ParseError) as exc_info:
            executor._parse_llm_response(response)

        assert "Invalid JSON response" in str(exc_info.value)

    # ========== Integration Tests ==========

    def test_end_to_end_execution(self, executor, mock_project, sample_input_data):
        """Test complete execution flow with realistic data."""
        result = executor.execute(mock_project, sample_input_data)

        # Basic assertions
        assert result['status'] == 'success'
        assert 'data' in result
        assert 'confidence' in result
        assert 'cached' in result
        assert 'execution_time_ms' in result

    def test_execution_with_empty_input(self, executor, mock_project):
        """Test execution with empty input data."""
        result = executor.execute(mock_project, {})

        # Should still execute successfully
        assert result['status'] == 'success'

    def test_execution_time_tracking(self, executor, mock_project, sample_input_data,
                                    mock_llm_client):
        """Test that execution time is properly tracked."""
        # Add a small delay to LLM call
        def delayed_generate(*args, **kwargs):
            import time
            time.sleep(0.01)  # 10ms delay
            return '{"result": "data"}'

        mock_llm_client.generate.side_effect = delayed_generate

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'success'
        assert result['execution_time_ms'] >= 10  # At least 10ms

    def test_failed_execution_time_tracking(self, executor, mock_project, sample_input_data,
                                          mock_llm_client):
        """Test that execution time is tracked even on failure."""
        mock_llm_client.generate.side_effect = Exception("Error")

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert result['execution_time_ms'] >= 0

    @patch('lookup.services.lookup_executor.logger')
    def test_unexpected_error_logging(self, mock_logger, executor, mock_project,
                                     sample_input_data):
        """Test that unexpected errors are logged."""
        # Create an error that will trigger the catch-all
        mock_project.template.template_text = None  # Will cause AttributeError

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'failed'
        assert 'Unexpected error' in result['error']
        mock_logger.exception.assert_called()

    def test_complex_llm_response(self, executor, mock_project, sample_input_data,
                                 mock_llm_client):
        """Test handling of complex nested LLM response."""
        complex_response = json.dumps({
            "vendor": {
                "canonical_name": "Slack Technologies",
                "id": "SLACK-001"
            },
            "categories": ["Communication", "SaaS"],
            "confidence": 0.88
        })
        mock_llm_client.generate.return_value = complex_response

        result = executor.execute(mock_project, sample_input_data)

        assert result['status'] == 'success'
        assert result['data']['vendor']['canonical_name'] == 'Slack Technologies'
        assert result['data']['categories'] == ['Communication', 'SaaS']
        assert result['confidence'] == 0.88
