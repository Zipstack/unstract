"""Parameterized integration tests for all LLM adapters.

This module provides comprehensive integration tests for all LLM providers
using pytest parametrization. Tests are automatically run for all providers
that have required environment variables configured.

The tests focus on real integration with external services while mocking
only Django/platform dependencies.

Required Environment Variables:
    See .env.test.sample for complete list of environment variables for each provider.

Example:
    # Run all tests for all configured providers
    pytest test_llm.py -v

    # Run tests for specific provider
    pytest test_llm.py -v -k "openai"

    # Run only connection tests
    pytest test_llm.py -v -k "connection"
"""

import pytest

from unstract.sdk1.llm import LLM

from .llm_test_config import PROVIDER_CONFIGS, get_available_providers


# Get list of available providers for parametrization
AVAILABLE_PROVIDERS = get_available_providers()

# If no providers are available, use a dummy list to allow pytest collection
# Tests will be skipped with helpful message
if not AVAILABLE_PROVIDERS:
    AVAILABLE_PROVIDERS = ["__no_providers_configured__"]


class TestLLMAdapters:
    """Parameterized integration tests for all LLM adapters."""

    # Test prompts used across all providers
    SIMPLE_PROMPT = "What is the capital of France?"
    COMPLEX_PROMPT = "Explain the concept of machine learning in 3 sentences."
    JSON_PROMPT = (
        'Return a JSON object with the capital of France. '
        'Format: {"country": "France", "capital": "..."}'
    )
    REASONING_PROMPT = "What is 15 * 24? Show your reasoning step by step."

    def _get_config_or_skip(self, provider_key: str):
        """Get provider config or skip test with helpful message.

        Args:
            provider_key: Provider identifier

        Returns:
            Provider configuration

        Raises:
            pytest.skip: If provider is not configured
        """
        # Check for dummy provider (no providers configured)
        if provider_key == "__no_providers_configured__":
            pytest.skip(
                "No LLM providers configured. Set environment variables in .env.test "
                "and run: export $(grep -v '^#' .env.test | xargs)"
            )

        config = PROVIDER_CONFIGS[provider_key]

        # Check if should skip
        should_skip, reason = config.should_skip()
        if should_skip:
            pytest.skip(reason)

        return config

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_connection(self, provider_key: str) -> None:
        """Test that the adapter can establish a connection.

        Args:
            provider_key: Provider identifier (e.g., 'openai', 'anthropic')
        """
        config = self._get_config_or_skip(provider_key)

        # Create LLM instance
        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Test connection
        try:
            result = llm.test_connection()
            assert result is True
            print(f"✅ {config.provider_name} adapter successfully established connection")
        except Exception as e:
            pytest.fail(f"{config.provider_name} adapter failed to connect: {str(e)}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_simple_completion(self, provider_key: str) -> None:
        """Test successful simple completion.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute completion
        result = llm.complete(self.SIMPLE_PROMPT)

        # Verify results
        assert result is not None
        assert "response" in result
        assert result["response"].text is not None
        assert "paris" in result["response"].text.lower()

        print(f"✅ {config.provider_name}: Successfully completed simple prompt")
        print(f"   Response: {result['response'].text[:100]}...")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_complex_completion(self, provider_key: str) -> None:
        """Test successful complex completion.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute completion
        result = llm.complete(self.COMPLEX_PROMPT)

        # Verify results
        assert result is not None
        assert "response" in result
        response_text = result["response"].text

        # Verify response contains relevant terms
        assert len(response_text) > 50
        assert "learning" in response_text.lower()

        print(f"✅ {config.provider_name}: Successfully completed complex prompt")
        print(f"   Response length: {len(response_text)} characters")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_streaming_completion(self, provider_key: str) -> None:
        """Test streaming completion.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Collect streamed chunks
        chunks = []
        for chunk in llm.stream_complete(self.SIMPLE_PROMPT):
            chunks.append(chunk)

        # Verify streaming worked
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0
        assert "paris" in full_response.lower()

        print(
            f"✅ {config.provider_name}: Successfully streamed completion in {len(chunks)} chunks"
        )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_json_extraction(self, provider_key: str) -> None:
        """Test JSON extraction from completion response.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute completion with JSON extraction
        result = llm.complete(self.JSON_PROMPT, extract_json=True)

        # Verify results
        assert result is not None
        assert "response" in result
        response_text = result["response"].text

        # Verify JSON-like structure is present
        assert "{" in response_text and "}" in response_text

        print(f"✅ {config.provider_name}: Successfully extracted JSON from response")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_custom_system_prompt(self, provider_key: str) -> None:
        """Test completion with custom system prompt.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        custom_system = "You are a helpful assistant that always responds in a friendly tone."
        llm = LLM(
            adapter_id=config.adapter_id,
            adapter_metadata=config.build_metadata(),
            system_prompt=custom_system,
        )

        # Execute completion
        result = llm.complete(self.SIMPLE_PROMPT)

        # Verify results
        assert result is not None
        assert "response" in result
        assert len(result["response"].text) > 0

        print(f"✅ {config.provider_name}: Successfully completed with custom system prompt")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_temperature_parameter(self, provider_key: str) -> None:
        """Test completion with different temperature settings.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        # Test with low temperature
        metadata_low_temp = config.build_metadata()
        metadata_low_temp["temperature"] = 0.1
        llm = LLM(adapter_id=config.adapter_id, adapter_metadata=metadata_low_temp)

        result = llm.complete(self.SIMPLE_PROMPT)

        assert result is not None
        assert "paris" in result["response"].text.lower()

        print(f"✅ {config.provider_name}: Successfully tested temperature parameters")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_max_tokens_parameter(self, provider_key: str) -> None:
        """Test completion with max_tokens limit.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        # Test with limited max_tokens
        metadata_limited = config.build_metadata()
        metadata_limited["max_tokens"] = 50
        llm = LLM(adapter_id=config.adapter_id, adapter_metadata=metadata_limited)

        # Execute completion
        result = llm.complete(self.COMPLEX_PROMPT)

        # Verify results
        assert result is not None
        response_text = result["response"].text

        # Response should be limited but not empty
        assert len(response_text) > 0
        assert len(response_text) < 500  # Rough estimate for 50 tokens

        print(f"✅ {config.provider_name}: Successfully limited response with max_tokens")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_get_model_name(self, provider_key: str) -> None:
        """Test retrieving the model name from LLM instance.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        model_name = llm.get_model_name()

        # Verify model name is correctly formatted
        assert model_name is not None
        # Model name should have provider prefix (e.g., "openai/", "anthropic/")
        assert "/" in model_name or "_" in model_name

        print(f"✅ {config.provider_name}: Successfully retrieved model name: {model_name}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_get_context_window_size(self, provider_key: str) -> None:
        """Test retrieving the context window size for the model.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        context_size = LLM.get_context_window_size(
            config.adapter_id, config.build_metadata()
        )

        # Verify context size is reasonable
        assert context_size is not None
        assert context_size > 0
        # Most modern LLMs have at least 4k context
        assert context_size >= 4000

        print(
            f"✅ {config.provider_name}: Successfully retrieved context window size: {context_size} tokens"
        )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_multiple_completions_sequential(self, provider_key: str) -> None:
        """Test multiple sequential completions to verify connection stability.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        prompts = [
            "What is 2+2?",
            "What is the capital of Japan?",
            "What color is the sky?",
        ]

        for idx, prompt in enumerate(prompts, 1):
            result = llm.complete(prompt)

            # Verify each result
            assert result is not None
            assert "response" in result
            assert len(result["response"].text) > 0

            print(f"   Completed sequential request {idx}/{len(prompts)}")

        print(
            f"✅ {config.provider_name}: Successfully completed multiple sequential requests"
        )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_reasoning_capability(self, provider_key: str) -> None:
        """Test model's reasoning capability with a math problem.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute completion
        result = llm.complete(self.REASONING_PROMPT)

        # Verify results
        assert result is not None
        response_text = result["response"].text

        # Check for the correct answer (360) somewhere in response
        assert "360" in response_text, f"Expected '360' in response, got: {response_text}"

        print(f"✅ {config.provider_name}: Successfully tested reasoning capability")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_retry_logic_with_timeout(self, provider_key: str) -> None:
        """Test that retry logic works with timeout settings.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        # Test with retry settings
        metadata_with_retry = config.build_metadata()
        metadata_with_retry["timeout"] = 30
        metadata_with_retry["max_retries"] = 2
        llm = LLM(adapter_id=config.adapter_id, adapter_metadata=metadata_with_retry)

        # Execute completion
        result = llm.complete(self.SIMPLE_PROMPT)

        # Verify results
        assert result is not None
        assert "response" in result

        print(f"✅ {config.provider_name}: Successfully tested retry logic with timeout")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_comprehensive_metadata_validation(self, provider_key: str) -> None:
        """Test that metadata is properly validated and processed.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Verify internal configuration
        assert llm.kwargs is not None
        assert "model" in llm.kwargs

        print(f"✅ {config.provider_name}: Successfully validated comprehensive metadata")
        print(f"   Validated fields: {list(llm.kwargs.keys())}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_response_format_consistency(self, provider_key: str) -> None:
        """Test that response format is consistent across multiple calls.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute multiple completions
        results = [llm.complete(self.SIMPLE_PROMPT) for _ in range(3)]

        # Verify all results have consistent format
        for idx, result in enumerate(results, 1):
            assert result is not None
            assert "response" in result
            assert hasattr(result["response"], "text")
            assert "paris" in result["response"].text.lower()

            print(f"   Response {idx} validated")

        print(
            f"✅ {config.provider_name}: Successfully verified response format consistency"
        )


# Error handling tests - these test with invalid credentials
class TestLLMErrorHandling:
    """Error handling tests for LLM adapters."""

    def _get_config_or_skip(self, provider_key: str):
        """Get provider config or skip test with helpful message.

        Args:
            provider_key: Provider identifier

        Returns:
            Provider configuration

        Raises:
            pytest.skip: If provider is not configured
        """
        # Check for dummy provider (no providers configured)
        if provider_key == "__no_providers_configured__":
            pytest.skip(
                "No LLM providers configured. Set environment variables in .env.test "
                "and run: export $(grep -v '^#' .env.test | xargs)"
            )

        config = PROVIDER_CONFIGS[provider_key]

        # Check if should skip
        should_skip, reason = config.should_skip()
        if should_skip:
            pytest.skip(reason)

        return config

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_invalid_credentials_error_handling(self, provider_key: str) -> None:
        """Test error handling with invalid credentials.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        # Build metadata with invalid credentials
        metadata = config.build_metadata()

        # Invalidate credentials based on provider type
        if "api_key" in metadata:
            metadata["api_key"] = "invalid-key-12345"
        elif "aws_access_key_id" in metadata:
            metadata["aws_access_key_id"] = "INVALID_KEY"
            metadata["aws_secret_access_key"] = "invalid_secret"
        elif "json_credentials" in metadata:
            metadata["json_credentials"] = '{"invalid": "credentials"}'
        elif "base_url" in metadata:
            metadata["base_url"] = "http://invalid:99999"

        llm = LLM(adapter_id=config.adapter_id, adapter_metadata=metadata)

        # Verify error is raised
        with pytest.raises(Exception) as exc_info:
            llm.complete("Test prompt")

        # Verify error message indicates authentication/connection issue
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message
            for keyword in ["api", "auth", "credential", "401", "403", "connect", "connection"]
        )

        print(f"✅ {config.provider_name}: Successfully handled invalid credentials error")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_empty_prompt_handling(self, provider_key: str) -> None:
        """Test handling of empty prompt.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        llm = LLM(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Execute with empty prompt - should still return a response
        result = llm.complete("")

        # Most providers will return something even for empty prompt
        assert result is not None
        assert "response" in result

        print(f"✅ {config.provider_name}: Successfully handled empty prompt")
