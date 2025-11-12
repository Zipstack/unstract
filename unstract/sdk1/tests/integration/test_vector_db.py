"""Integration tests for VectorDB adapters.

This module tests VectorDB adapters across different providers using pytest
parameterization. Tests validate connection, basic operations, and error handling.

VectorDB adapters use LlamaIndex (not LiteLLM like LLM/Embedding), so the test
patterns are similar but adapted for the VectorDB interface.

To run tests for all configured providers:
    pytest test_vector_db.py -v

To run tests for a specific provider:
    pytest test_vector_db.py -v -k "[milvus]"
    pytest test_vector_db.py -v -k "[pinecone]"

Note: Tests automatically skip providers without configured credentials.
"""

import pytest
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk1.exceptions import VectorDBError
from vectordb_test_config import AVAILABLE_PROVIDERS, PROVIDER_CONFIGS


class TestVectorDBAdapters:
    """Test suite for VectorDB adapter integration testing.

    Tests are parameterized across all available VectorDB providers.
    Each test method validates a specific aspect of the VectorDB adapter.
    """

    def _get_config_or_skip(self, provider_key: str):
        """Get provider config or skip test if not available.

        Args:
            provider_key: Provider identifier (e.g., "milvus", "pinecone")

        Returns:
            VectorDBProviderConfig instance

        Raises:
            pytest.skip: If provider is not configured or is dummy provider
        """
        if provider_key == "dummy":
            pytest.skip("No VectorDB providers configured - set environment variables")

        config = PROVIDER_CONFIGS.get(provider_key)
        if not config:
            pytest.skip(f"Provider {provider_key} not found in configuration")

        if config.skip_reason:
            pytest.skip(config.skip_reason)

        if not config.is_available():
            missing_vars = [
                var for var in config.required_env_vars if not config.is_available()
            ]
            pytest.skip(
                f"Skipping {config.provider_name} - missing environment variables: "
                f"{', '.join(config.required_env_vars)}"
            )

        return config

    # ============================================================================
    # Core Functionality Tests (3 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_connection(self, provider_key: str):
        """Test basic connection to VectorDB provider.

        Validates that the VectorDB adapter can successfully connect to the
        configured provider and return a working vector store instance.

        Note: Unlike LLM/Embedding, VectorDB test_connection creates and deletes
        a test collection internally.
        """
        config = self._get_config_or_skip(provider_key)

        # Initialize adapter with metadata
        # VectorDB adapters expect settings dict in __init__
        adapter = config.adapter_class(settings=config.build_metadata())

        # Test connection (this creates and deletes a test collection)
        result = adapter.test_connection()

        assert result is True, f"{config.provider_name} connection test failed"

        # Cleanup
        adapter.close()

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_get_vector_db_instance(self, provider_key: str):
        """Test getting vector database instance from adapter.

        Validates that the adapter can return a valid LlamaIndex VectorStore instance.
        """
        config = self._get_config_or_skip(provider_key)

        # Initialize adapter with metadata
        adapter = config.adapter_class(settings=config.build_metadata())

        # Get vector store instance
        vector_store = adapter.get_vector_db_instance()

        # Verify vector store is valid
        assert vector_store is not None, f"{config.provider_name} returned None instance"

        # Verify it's a LlamaIndex VectorStore
        from llama_index.core.vector_stores.types import BasePydanticVectorStore

        assert isinstance(
            vector_store, BasePydanticVectorStore
        ), f"{config.provider_name} did not return BasePydanticVectorStore"

        # Cleanup
        adapter.close()

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_adapter_metadata(self, provider_key: str):
        """Test adapter metadata and configuration.

        Validates that the adapter has correct static metadata including
        ID, name, description, and icon.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Verify adapter ID matches configuration
        assert (
            adapter_class.get_id() == config.adapter_id
        ), f"Adapter ID mismatch for {config.provider_name}"

        # Verify adapter has required metadata
        assert (
            adapter_class.get_name() == config.provider_name
        ), f"Adapter name mismatch for {config.provider_name}"
        assert (
            adapter_class.get_description()
        ), f"{config.provider_name} missing description"
        assert adapter_class.get_icon(), f"{config.provider_name} missing icon"

    # ============================================================================
    # Configuration Tests (3 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_custom_collection_name(self, provider_key: str):
        """Test adapter with custom collection/table name.

        Validates that adapters correctly handle custom collection names
        in their metadata configuration.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Build metadata with custom collection name
        metadata = config.build_metadata()
        custom_name = "test_custom_collection"
        metadata["vector_db_name"] = custom_name

        # Create adapter
        adapter = adapter_class(settings=metadata)
        assert adapter is not None, f"Failed to create {config.provider_name} adapter"

        # Verify collection name is set (note: actual name may have prefix/suffix)
        assert adapter._collection_name, f"{config.provider_name} collection name not set"

        # Cleanup
        adapter.close()

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_custom_embedding_dimension(self, provider_key: str):
        """Test adapter with custom embedding dimension.

        Validates that adapters correctly handle different embedding dimensions
        in their configuration.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Build metadata with custom dimension
        metadata = config.build_metadata()
        custom_dim = 768  # Common for smaller embedding models
        metadata["embedding_dimension"] = custom_dim

        # Create adapter
        adapter = adapter_class(settings=metadata)
        assert adapter is not None, f"Failed to create {config.provider_name} adapter"

        # Verify adapter was created successfully
        vector_store = adapter.get_vector_db_instance()
        assert (
            vector_store is not None
        ), f"{config.provider_name} failed with custom dimension"

        # Cleanup
        adapter.close()

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_default_configuration_values(self, provider_key: str):
        """Test adapter with default configuration values.

        Validates that adapters correctly apply default values for optional
        configuration parameters.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Build minimal metadata (only required fields)
        metadata = config.build_metadata()

        # Remove optional fields to test defaults
        optional_fields = ["vector_db_name", "embedding_dimension"]
        for field in optional_fields:
            if field in metadata:
                del metadata[field]

        # Create adapter with minimal config
        adapter = adapter_class(settings=metadata)
        assert adapter is not None, f"Failed to create {config.provider_name} adapter"

        # Verify default collection name is applied
        assert (
            adapter._collection_name == VectorDbConstants.DEFAULT_VECTOR_DB_NAME
            or VectorDbConstants.DEFAULT_VECTOR_DB_NAME in adapter._collection_name
        ), f"{config.provider_name} did not apply default collection name"

        # Cleanup
        adapter.close()

    # ============================================================================
    # Error Handling Tests (3 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_invalid_credentials(self, provider_key: str):
        """Test adapter behavior with invalid credentials.

        Validates that adapters properly handle and report authentication failures.
        """
        config = self._get_config_or_skip(provider_key)

        # Skip providers that don't use credentials
        if provider_key in ["postgres", "supabase", "milvus"]:
            # These may not fail immediately with invalid creds
            pytest.skip(f"{config.provider_name} may not validate credentials at init")

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Build metadata with invalid credentials
        metadata = config.build_metadata()
        if "api_key" in metadata:
            metadata["api_key"] = "invalid-api-key-12345"
        elif "token" in metadata:
            metadata["token"] = "invalid-token-12345"

        # Attempt to create adapter and test connection
        with pytest.raises((AdapterError, VectorDBError, Exception)) as exc_info:
            adapter = adapter_class(settings=metadata)
            adapter.test_connection()
            adapter.close()

        # Verify error message indicates authentication issue
        error_msg = str(exc_info.value).lower()
        auth_keywords = [
            "auth",
            "credential",
            "api key",
            "token",
            "forbidden",
            "unauthorized",
            "invalid",
        ]
        assert any(
            keyword in error_msg for keyword in auth_keywords
        ), f"{config.provider_name} error message doesn't indicate auth issue: {error_msg}"

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_missing_required_fields(self, provider_key: str):
        """Test adapter behavior with missing required configuration fields.

        Validates that adapters properly validate required configuration parameters.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Create empty metadata (missing required fields)
        empty_metadata = {}

        # Attempt to create adapter with empty config
        with pytest.raises(
            (AdapterError, VectorDBError, ValueError, KeyError, Exception)
        ):
            adapter = adapter_class(settings=empty_metadata)
            # Some adapters may fail on get_vector_db_instance or test_connection
            adapter.get_vector_db_instance()
            adapter.close()

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_invalid_host_or_url(self, provider_key: str):
        """Test adapter behavior with invalid host or URL.

        Validates that adapters properly handle connection failures.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.vectordb.register import VectorDBRegistry

        adapter_class = VectorDBRegistry.get_adapter_class_by_adapter_id(
            config.adapter_id
        )

        # Build metadata with invalid host/URL
        metadata = config.build_metadata()
        if "url" in metadata:
            metadata["url"] = "https://invalid-vectordb-host-12345.example.com"
        elif "host" in metadata:
            metadata["host"] = "invalid-vectordb-host-12345.example.com"
        elif "uri" in metadata:
            metadata["uri"] = "https://invalid-vectordb-host-12345.example.com"

        # Attempt to connect
        with pytest.raises((AdapterError, VectorDBError, Exception)) as exc_info:
            adapter = adapter_class(settings=metadata)
            adapter.test_connection()
            adapter.close()

        # Verify error indicates connection issue
        error_msg = str(exc_info.value).lower()
        connection_keywords = [
            "connect",
            "host",
            "url",
            "timeout",
            "network",
            "unreachable",
            "not found",
        ]
        assert any(
            keyword in error_msg for keyword in connection_keywords
        ), f"{config.provider_name} error doesn't indicate connection issue: {error_msg}"

    # ============================================================================
    # Cleanup Tests (1 test)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_adapter_close(self, provider_key: str):
        """Test proper cleanup of adapter resources.

        Validates that adapters correctly implement close() method for
        resource cleanup.
        """
        config = self._get_config_or_skip(provider_key)

        # Initialize adapter with metadata
        adapter = config.adapter_class(settings=config.build_metadata())

        # Get instance to ensure connection is established
        adapter.get_vector_db_instance()

        # Close should not raise exception
        adapter.close()

        # Calling close again should be safe
        adapter.close()
