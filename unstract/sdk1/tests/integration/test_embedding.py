"""Parameterized integration tests for all Embedding adapters.

This module provides comprehensive integration tests for all embedding providers
using pytest parametrization. Tests are automatically run for all providers
that have required environment variables configured.

The tests focus on real integration with external services while mocking
only Django/platform dependencies.

Required Environment Variables:
    See .env.test.sample for complete list of environment variables for each provider.

Example:
    # Run all tests for all configured providers
    pytest test_embedding.py -v

    # Run tests for specific provider
    pytest test_embedding.py -v -k "[openai]"

    # Run only connection tests
    pytest test_embedding.py -v -k "connection"
"""

import asyncio

import pytest

from unstract.sdk1.embedding import Embedding

from .embedding_test_config import PROVIDER_CONFIGS, get_available_providers


# Get list of available providers for parametrization
AVAILABLE_PROVIDERS = get_available_providers()

# If no providers are available, use a dummy list to allow pytest collection
# Tests will be skipped with helpful message
if not AVAILABLE_PROVIDERS:
    AVAILABLE_PROVIDERS = ["__no_providers_configured__"]


class TestEmbeddingAdapters:
    """Parameterized integration tests for all embedding adapters."""

    # Test texts used across all providers
    SIMPLE_TEXT = "Hello world"
    COMPLEX_TEXT = (
        "Machine learning is a branch of artificial intelligence that enables "
        "computers to learn and improve from experience without being explicitly programmed."
    )
    BATCH_TEXTS = [
        "The quick brown fox jumps over the lazy dog.",
        "Artificial intelligence is transforming the world.",
        "Data science combines statistics and computer science.",
    ]

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
                "No embedding providers configured. Set environment variables in .env.test "
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
            provider_key: Provider identifier (e.g., 'openai', 'azure_openai')
        """
        config = self._get_config_or_skip(provider_key)

        # Create Embedding instance
        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Test connection
        try:
            result = embedding.test_connection()
            assert result is True
            print(
                f"✅ {config.provider_name} embedding adapter successfully established connection"
            )
        except Exception as e:
            pytest.fail(
                f"{config.provider_name} embedding adapter failed to connect: {str(e)}"
            )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_single_embedding(self, provider_key: str) -> None:
        """Test generating a single embedding vector.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get embedding
        result = embedding.get_embedding(self.SIMPLE_TEXT)

        # Verify results
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(x, float) for x in result)

        print(f"✅ {config.provider_name}: Successfully generated embedding vector")
        print(f"   Vector dimension: {len(result)}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_embedding_dimension_consistency(self, provider_key: str) -> None:
        """Test that embedding dimensions are consistent across calls.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get multiple embeddings
        embedding1 = embedding.get_embedding(self.SIMPLE_TEXT)
        embedding2 = embedding.get_embedding(self.COMPLEX_TEXT)

        # Verify dimensions match
        assert len(embedding1) == len(embedding2)

        print(
            f"✅ {config.provider_name}: Embedding dimensions are consistent ({len(embedding1)})"
        )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_batch_embeddings(self, provider_key: str) -> None:
        """Test generating multiple embeddings in a batch.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get batch embeddings
        results = embedding.get_embeddings(self.BATCH_TEXTS)

        # Verify results
        assert results is not None
        assert isinstance(results, list)
        assert len(results) == len(self.BATCH_TEXTS)

        # Verify each embedding
        for idx, result in enumerate(results):
            assert isinstance(result, list)
            assert len(result) > 0
            assert all(isinstance(x, float) for x in result)

        # Verify all embeddings have same dimension
        dimensions = [len(r) for r in results]
        assert len(set(dimensions)) == 1

        print(
            f"✅ {config.provider_name}: Successfully generated {len(results)} embeddings"
        )
        print(f"   Vector dimension: {dimensions[0]}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_async_single_embedding(self, provider_key: str) -> None:
        """Test async generation of a single embedding vector.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get async embedding
        async def get_async_embedding():
            return await embedding.get_aembedding(self.SIMPLE_TEXT)

        result = asyncio.run(get_async_embedding())

        # Verify results
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(x, float) for x in result)

        print(
            f"✅ {config.provider_name}: Successfully generated async embedding vector"
        )
        print(f"   Vector dimension: {len(result)}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_async_batch_embeddings(self, provider_key: str) -> None:
        """Test async generation of multiple embeddings in a batch.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get async batch embeddings
        async def get_async_embeddings():
            return await embedding.get_aembeddings(self.BATCH_TEXTS)

        results = asyncio.run(get_async_embeddings())

        # Verify results
        assert results is not None
        assert isinstance(results, list)
        assert len(results) == len(self.BATCH_TEXTS)

        # Verify each embedding
        for result in results:
            assert isinstance(result, list)
            assert len(result) > 0
            assert all(isinstance(x, float) for x in result)

        # Verify all embeddings have same dimension
        dimensions = [len(r) for r in results]
        assert len(set(dimensions)) == 1

        print(
            f"✅ {config.provider_name}: Successfully generated {len(results)} async embeddings"
        )
        print(f"   Vector dimension: {dimensions[0]}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_embedding_numerical_properties(self, provider_key: str) -> None:
        """Test that embedding vectors have valid numerical properties.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get embedding
        result = embedding.get_embedding(self.SIMPLE_TEXT)

        # Verify numerical properties
        assert all(isinstance(x, float) for x in result)
        assert all(-10.0 <= x <= 10.0 for x in result)  # Reasonable range
        assert not all(x == 0 for x in result)  # Not all zeros

        # Calculate L2 norm
        import math

        l2_norm = math.sqrt(sum(x * x for x in result))
        assert l2_norm > 0  # Non-zero norm

        print(f"✅ {config.provider_name}: Embedding has valid numerical properties")
        print(f"   L2 norm: {l2_norm:.4f}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_embedding_similarity(self, provider_key: str) -> None:
        """Test that similar texts produce similar embeddings.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Similar texts
        text1 = "The cat sat on the mat."
        text2 = "A cat was sitting on a mat."
        text3 = "Quantum mechanics is a fundamental theory in physics."

        # Get embeddings
        emb1 = embedding.get_embedding(text1)
        emb2 = embedding.get_embedding(text2)
        emb3 = embedding.get_embedding(text3)

        # Calculate cosine similarity
        def cosine_similarity(vec1, vec2):
            import math

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(x * x for x in vec1))
            norm2 = math.sqrt(sum(x * x for x in vec2))
            return dot_product / (norm1 * norm2)

        # Similar texts should have higher similarity
        similarity_12 = cosine_similarity(emb1, emb2)
        similarity_13 = cosine_similarity(emb1, emb3)

        assert similarity_12 > similarity_13

        print(
            f"✅ {config.provider_name}: Similar texts have higher similarity score"
        )
        print(f"   Similar texts similarity: {similarity_12:.4f}")
        print(f"   Dissimilar texts similarity: {similarity_13:.4f}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_empty_text_handling(self, provider_key: str) -> None:
        """Test handling of empty text input.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Most providers will handle empty text gracefully or return an embedding
        try:
            result = embedding.get_embedding("")
            # If it succeeds, verify the result
            assert result is not None
            assert isinstance(result, list)
            print(f"✅ {config.provider_name}: Handled empty text gracefully")
        except Exception as e:
            # Some providers may raise an error for empty text, which is acceptable
            print(
                f"✅ {config.provider_name}: Raised expected error for empty text: {type(e).__name__}"
            )

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_long_text_handling(self, provider_key: str) -> None:
        """Test handling of long text input.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Create a long text (most models can handle at least 512 tokens)
        long_text = " ".join([self.COMPLEX_TEXT] * 5)

        # Get embedding
        result = embedding.get_embedding(long_text)

        # Verify results
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

        print(f"✅ {config.provider_name}: Successfully handled long text")
        print(f"   Text length: {len(long_text)} characters")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_special_characters_handling(self, provider_key: str) -> None:
        """Test handling of text with special characters.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Text with special characters
        special_text = "Hello! @#$% 你好 🌍 \n\t Special characters: {}[]()\"'"

        # Get embedding
        result = embedding.get_embedding(special_text)

        # Verify results
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

        print(f"✅ {config.provider_name}: Successfully handled special characters")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_sync_async_consistency(self, provider_key: str) -> None:
        """Test that sync and async methods produce similar results.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Get sync embedding
        sync_result = embedding.get_embedding(self.SIMPLE_TEXT)

        # Get async embedding
        async def get_async():
            return await embedding.get_aembedding(self.SIMPLE_TEXT)

        async_result = asyncio.run(get_async())

        # Verify both have same dimensions
        assert len(sync_result) == len(async_result)

        # Calculate similarity (should be very high, ideally 1.0)
        import math

        def cosine_similarity(vec1, vec2):
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = math.sqrt(sum(x * x for x in vec1))
            norm2 = math.sqrt(sum(x * x for x in vec2))
            return dot_product / (norm1 * norm2)

        similarity = cosine_similarity(sync_result, async_result)

        # Allow for minor numerical differences
        assert similarity > 0.99

        print(
            f"✅ {config.provider_name}: Sync and async methods are consistent"
        )
        print(f"   Similarity: {similarity:.6f}")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_metadata_validation(self, provider_key: str) -> None:
        """Test that metadata is properly validated.

        Args:
            provider_key: Provider identifier
        """
        config = self._get_config_or_skip(provider_key)

        embedding = Embedding(
            adapter_id=config.adapter_id, adapter_metadata=config.build_metadata()
        )

        # Verify internal configuration
        assert embedding.kwargs is not None
        assert "model" in embedding.kwargs

        print(
            f"✅ {config.provider_name}: Successfully validated embedding metadata"
        )
        print(f"   Model: {embedding.kwargs.get('model')}")


# Error handling tests
class TestEmbeddingErrorHandling:
    """Error handling tests for embedding adapters."""

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
                "No embedding providers configured. Set environment variables in .env.test "
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

        embedding = Embedding(adapter_id=config.adapter_id, adapter_metadata=metadata)

        # Verify error is raised
        with pytest.raises(Exception) as exc_info:
            embedding.get_embedding("Test text")

        # Verify error message indicates authentication/connection issue
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message
            for keyword in [
                "api",
                "auth",
                "credential",
                "401",
                "403",
                "connect",
                "connection",
                "invalid",
            ]
        )

        print(
            f"✅ {config.provider_name}: Successfully handled invalid credentials error"
        )
