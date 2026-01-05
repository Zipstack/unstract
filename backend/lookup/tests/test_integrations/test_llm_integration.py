"""
Tests for LLM provider integration.
"""

import json
from unittest.mock import patch

from django.test import TestCase

from ...integrations.llm_provider import (
    UnstractLLMClient,
    OpenAILLMClient,
    AnthropicLLMClient
)


class UnstractLLMClientTest(TestCase):
    """Test cases for UnstractLLMClient."""

    def setUp(self):
        """Set up test fixtures."""
        # Patch environment variables
        self.env_patcher = patch('lookup.integrations.llm_provider.os.getenv')
        self.mock_getenv = self.env_patcher.start()
        self.mock_getenv.side_effect = self._mock_getenv

        # Initialize client
        self.client = UnstractLLMClient()

    def tearDown(self):
        """Clean up patches."""
        self.env_patcher.stop()

    def _mock_getenv(self, key, default=None):
        """Mock environment variables."""
        env_vars = {
            'LOOKUP_DEFAULT_LLM_PROVIDER': 'openai',
            'LOOKUP_DEFAULT_LLM_MODEL': 'gpt-4',
            'OPENAI_API_KEY': 'test-openai-key',
            'ANTHROPIC_API_KEY': 'test-anthropic-key',
            'AZURE_OPENAI_API_KEY': 'test-azure-key',
            'AZURE_OPENAI_ENDPOINT': 'https://test.azure.com'
        }
        return env_vars.get(key, default)

    def test_initialization(self):
        """Test client initialization."""
        # Test default initialization
        client = UnstractLLMClient()
        self.assertEqual(client.default_provider, 'openai')
        self.assertEqual(client.default_model, 'gpt-4')

        # Test custom initialization
        client = UnstractLLMClient(provider='anthropic', model='claude-2')
        self.assertEqual(client.default_provider, 'anthropic')
        self.assertEqual(client.default_model, 'claude-2')

    def test_generate_with_valid_json(self):
        """Test generation with valid JSON response."""
        prompt = "Extract vendor information"
        config = {
            'provider': 'openai',
            'model': 'gpt-4',
            'temperature': 0.7
        }

        # Since we don't have actual LLM integration, test fallback
        response = self.client.generate(prompt, config)

        # Verify response is valid JSON
        data = json.loads(response)
        self.assertIsInstance(data, dict)

        # Should have confidence score
        if 'confidence' in data:
            self.assertTrue(0 <= data['confidence'] <= 1)

    def test_generate_with_timeout(self):
        """Test generation respects timeout."""
        import time
        start = time.time()

        response = self.client.generate(
            "Test prompt",
            {'provider': 'openai'},
            timeout=1
        )

        elapsed = time.time() - start

        # Should complete within reasonable time
        self.assertLess(elapsed, 2)
        self.assertIsNotNone(response)

    def test_extract_json_from_text(self):
        """Test JSON extraction from mixed text."""
        # Test with embedded JSON
        text = "Here is the result: {\"vendor\": \"Test Corp\", \"confidence\": 0.9} end of response"
        result = self.client._extract_json(text)

        data = json.loads(result)
        self.assertEqual(data['vendor'], 'Test Corp')
        self.assertEqual(data['confidence'], 0.9)

        # Test with no valid JSON
        text = "No JSON here"
        result = self.client._extract_json(text)

        data = json.loads(result)
        self.assertIn('raw_response', data)
        self.assertIn('warning', data)

    def test_validate_response(self):
        """Test response validation."""
        # Valid response
        valid_response = json.dumps({
            'vendor': 'Test',
            'confidence': 0.85
        })
        self.assertTrue(self.client.validate_response(valid_response))

        # Missing confidence
        no_confidence = json.dumps({'vendor': 'Test'})
        self.assertFalse(self.client.validate_response(no_confidence))

        # Invalid confidence
        bad_confidence = json.dumps({'confidence': 1.5})
        self.assertFalse(self.client.validate_response(bad_confidence))

        # Invalid JSON
        not_json = "not json"
        self.assertFalse(self.client.validate_response(not_json))

    def test_get_token_count(self):
        """Test token counting estimation."""
        # Test basic estimation
        text = "This is a test prompt with some content"
        count = self.client.get_token_count(text)

        # Should be roughly len/4
        expected = len(text) // 4
        self.assertAlmostEqual(count, expected, delta=2)

        # Test empty text
        self.assertEqual(self.client.get_token_count(""), 0)

    def test_fallback_generation(self):
        """Test fallback generation when LLM unavailable."""
        # Force fallback mode
        self.client.llm_available = False

        response = self.client.generate(
            "vendor extraction prompt",
            {'provider': 'openai'}
        )

        # Should return valid JSON
        data = json.loads(response)
        self.assertEqual(data['status'], 'fallback')
        self.assertIn('canonical_vendor', data)

    def test_simulate_llm_call(self):
        """Test simulated LLM call."""
        # Test vendor prompt
        vendor_response = self.client._simulate_llm_call(
            "Extract vendor information",
            {'provider': 'openai'}
        )
        vendor_data = json.loads(vendor_response)
        self.assertIn('canonical_vendor', vendor_data)
        self.assertIn('vendor_category', vendor_data)

        # Test product prompt
        product_response = self.client._simulate_llm_call(
            "Extract product details",
            {'provider': 'openai'}
        )
        product_data = json.loads(product_response)
        self.assertIn('product_name', product_data)
        self.assertIn('product_category', product_data)


class OpenAILLMClientTest(TestCase):
    """Test cases for OpenAI-specific client."""

    def test_openai_client_initialization(self):
        """Test OpenAI client initialization."""
        client = OpenAILLMClient()
        self.assertEqual(client.default_provider, 'openai')
        self.assertEqual(client.default_model, 'gpt-4')

    @patch('lookup.integrations.llm_provider.UnstractLLMClient.generate')
    def test_openai_generate(self, mock_generate):
        """Test OpenAI-specific generation."""
        mock_generate.return_value = '{"result": "test"}'

        client = OpenAILLMClient()
        response = client.generate(
            "test prompt",
            {'temperature': 0.5}
        )

        # Verify OpenAI config was used
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args[0]
        config = call_args[1]

        self.assertEqual(config['provider'], 'openai')
        self.assertEqual(config['temperature'], 0.5)


class AnthropicLLMClientTest(TestCase):
    """Test cases for Anthropic-specific client."""

    def test_anthropic_client_initialization(self):
        """Test Anthropic client initialization."""
        client = AnthropicLLMClient()
        self.assertEqual(client.default_provider, 'anthropic')
        self.assertEqual(client.default_model, 'claude-2')

    @patch('lookup.integrations.llm_provider.UnstractLLMClient.generate')
    def test_anthropic_generate(self, mock_generate):
        """Test Anthropic-specific generation."""
        mock_generate.return_value = '{"result": "test"}'

        client = AnthropicLLMClient()
        response = client.generate(
            "test prompt",
            {'temperature': 0.8}
        )

        # Verify Anthropic config was used
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args[0]
        config = call_args[1]

        self.assertEqual(config['provider'], 'anthropic')
        self.assertEqual(config['model'], 'claude-2')
        self.assertEqual(config['temperature'], 0.8)
