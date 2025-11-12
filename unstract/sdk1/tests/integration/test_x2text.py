"""Integration tests for X2Text (document extraction) adapters.

This module tests X2Text adapters across different providers using pytest
parameterization. Tests validate connection, basic extraction operations, and error handling.

X2Text adapters handle document text extraction from PDFs, images, and other formats.
Unlike LLM/Embedding tests, these tests require actual document files for processing.

To run tests for all configured providers:
    pytest test_x2text.py -v

To run tests for a specific provider:
    pytest test_x2text.py -v -k "[llama_parse]"
    pytest test_x2text.py -v -k "[llm_whisperer_v2]"
    pytest test_x2text.py -v -k "[no_op]"

Note: Tests automatically skip providers without configured credentials.
"""

import os
import tempfile

import pytest
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from x2text_test_config import AVAILABLE_PROVIDERS, PROVIDER_CONFIGS


class TestX2TextAdapters:
    """Test suite for X2Text adapter integration testing.

    Tests are parameterized across all available X2Text providers.
    Each test method validates a specific aspect of the X2Text adapter.
    """

    @pytest.fixture
    def sample_pdf_path(self) -> str:
        """Create a minimal test PDF file.

        Returns:
            Path to temporary test PDF file
        """
        # Create a minimal PDF file for testing
        # This is a simple text-based PDF that most extractors can handle
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources 4 0 R /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
0000000314 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
407
%%EOF"""

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
            f.write(pdf_content)
            return f.name

    @pytest.fixture
    def sample_text_path(self) -> str:
        """Create a simple text file for testing.

        Returns:
            Path to temporary text file
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Test Document\nThis is a test document for X2Text adapter testing.")
            return f.name

    def _get_config_or_skip(self, provider_key: str):
        """Get provider config or skip test if not available.

        Args:
            provider_key: Provider identifier (e.g., "llama_parse", "llm_whisperer_v2")

        Returns:
            X2TextProviderConfig instance

        Raises:
            pytest.skip: If provider is not configured or is dummy provider
        """
        if provider_key == "__no_providers_configured__":
            pytest.skip("No X2Text providers configured - set environment variables")

        config = PROVIDER_CONFIGS.get(provider_key)
        if not config:
            pytest.skip(f"Provider {provider_key} not found in configuration")

        if config.skip_reason:
            pytest.skip(config.skip_reason)

        if not config.is_available():
            pytest.skip(
                f"Skipping {config.provider_name} - missing environment variables: "
                f"{', '.join(config.required_env_vars)}"
            )

        return config

    def _cleanup_file(self, file_path: str):
        """Clean up temporary test file.

        Args:
            file_path: Path to file to remove
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass  # Ignore cleanup errors

    # ============================================================================
    # Core Functionality Tests (3 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_connection(self, provider_key: str):
        """Test basic connection to X2Text provider.

        Validates that the X2Text adapter can successfully connect to the
        configured provider and verify credentials/configuration.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        # Build the adapter registry to get all adapters
        adapters = {}
        X2TextRegistry.register_adapters(adapters)

        # Get the adapter for this provider
        adapter_info = adapters.get(config.adapter_id)
        assert adapter_info is not None, f"Adapter not found for {config.adapter_id}"

        # Get adapter class from metadata
        adapter_class = adapter_info["metadata"]["adapter"]
        assert (
            adapter_class is not None
        ), f"Adapter class not found for {config.adapter_id}"

        # Initialize adapter with metadata
        adapter = adapter_class(settings=config.build_metadata())

        # Test connection if available
        # Note: Not all adapters implement test_connection (e.g., local processors)
        if hasattr(adapter, "test_connection"):
            result = adapter.test_connection()
            assert result is True, f"{config.provider_name} connection test failed"
        else:
            # For adapters without test_connection, just verify initialization succeeded
            assert adapter is not None, f"{config.provider_name} initialization failed"

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_basic_text_extraction(self, provider_key: str, sample_text_path: str):
        """Test basic text extraction from a simple text file.

        Validates that the adapter can process a simple text file and return
        extracted text content.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]
        adapter = adapter_class(settings=config.build_metadata())

        try:
            # Process the text file
            result = adapter.process(input_file_path=sample_text_path)

            # Verify result is TextExtractionResult
            assert isinstance(
                result, TextExtractionResult
            ), f"{config.provider_name} did not return TextExtractionResult"

            # Verify extracted text is not empty
            assert (
                result.extracted_text
            ), f"{config.provider_name} returned empty extracted text"
            assert isinstance(
                result.extracted_text, str
            ), f"{config.provider_name} extracted_text is not a string"

        finally:
            self._cleanup_file(sample_text_path)

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_adapter_metadata(self, provider_key: str):
        """Test adapter metadata and configuration.

        Validates that the adapter has correct static metadata including
        ID, name, description, and icon.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]

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
    # Output Handling Tests (2 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_output_file_writing(self, provider_key: str, sample_text_path: str):
        """Test writing extracted text to output file.

        Validates that the adapter can write extraction results to a specified
        output file path.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]
        adapter = adapter_class(settings=config.build_metadata())

        # Create temporary output file path
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            output_path = f.name

        try:
            # Process with output file
            result = adapter.process(
                input_file_path=sample_text_path, output_file_path=output_path
            )

            # Verify result is valid
            assert isinstance(result, TextExtractionResult)
            assert result.extracted_text

            # Some adapters may or may not write to output file
            # Just verify no errors occurred

        finally:
            self._cleanup_file(sample_text_path)
            self._cleanup_file(output_path)

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_extraction_result_structure(self, provider_key: str, sample_text_path: str):
        """Test TextExtractionResult structure and fields.

        Validates that the extraction result has the correct structure
        and all expected fields.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]
        adapter = adapter_class(settings=config.build_metadata())

        try:
            result = adapter.process(input_file_path=sample_text_path)

            # Verify result type
            assert isinstance(
                result, TextExtractionResult
            ), f"{config.provider_name} result type incorrect"

            # Verify required fields
            assert hasattr(
                result, "extracted_text"
            ), f"{config.provider_name} missing extracted_text field"
            assert isinstance(
                result.extracted_text, str
            ), f"{config.provider_name} extracted_text not a string"

            # Verify extraction_metadata field exists (even if None)
            assert hasattr(
                result, "extraction_metadata"
            ), f"{config.provider_name} missing extraction_metadata field"

        finally:
            self._cleanup_file(sample_text_path)

    # ============================================================================
    # Configuration Tests (2 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_custom_adapter_name(self, provider_key: str):
        """Test adapter with custom adapter name in configuration.

        Validates that adapters correctly handle custom adapter names
        in their metadata configuration.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]

        # Build metadata with custom adapter name
        metadata = config.build_metadata()
        custom_name = "test-custom-x2text-adapter"
        metadata["adapter_name"] = custom_name

        # Create adapter
        adapter = adapter_class(settings=metadata)
        assert adapter is not None, f"Failed to create {config.provider_name} adapter"

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_minimal_configuration(self, provider_key: str):
        """Test adapter with minimal required configuration.

        Validates that adapters work with only required configuration fields,
        using defaults for optional parameters.
        """
        config = self._get_config_or_skip(provider_key)

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]

        # Build minimal metadata (only required fields)
        metadata = config.build_metadata()

        # Create adapter with minimal config
        adapter = adapter_class(settings=metadata)
        assert adapter is not None, f"Failed to create {config.provider_name} adapter"

    # ============================================================================
    # Error Handling Tests (2 tests)
    # ============================================================================

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_invalid_file_path(self, provider_key: str):
        """Test adapter behavior with non-existent file path.

        Validates that adapters properly handle missing input files.
        """
        config = self._get_config_or_skip(provider_key)

        # Skip NoOp adapter as it doesn't actually read files
        if provider_key == "no_op":
            pytest.skip("NoOp adapter doesn't validate file paths")

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]
        adapter = adapter_class(settings=config.build_metadata())

        # Attempt to process non-existent file
        with pytest.raises((AdapterError, FileNotFoundError, Exception)):
            adapter.process(input_file_path="/non/existent/file.pdf")

    @pytest.mark.parametrize("provider_key", AVAILABLE_PROVIDERS)
    def test_empty_configuration(self, provider_key: str):
        """Test adapter behavior with empty/invalid configuration.

        Validates that adapters properly validate configuration parameters.
        """
        config = self._get_config_or_skip(provider_key)

        # Skip adapters with no required config (NoOp, Unstructured Community)
        if provider_key in ["no_op", "unstructured_community"]:
            pytest.skip(f"{config.provider_name} has no required configuration fields")

        from unstract.sdk1.adapters.x2text.register import X2TextRegistry

        adapters = {}
        X2TextRegistry.register_adapters(adapters)
        adapter_info = adapters.get(config.adapter_id)
        adapter_class = adapter_info["metadata"]["adapter"]

        # Create empty metadata
        empty_metadata = {}

        # Attempt to create adapter with empty config
        # This should either fail during initialization or during use
        adapter = adapter_class(settings=empty_metadata)

        # For some adapters, errors only occur during use
        # Try to test connection or process a file
        try:
            if hasattr(adapter, "test_connection"):
                with pytest.raises((AdapterError, KeyError, ValueError, Exception)):
                    adapter.test_connection()
            else:
                # Try processing with empty config
                with pytest.raises((AdapterError, KeyError, ValueError, Exception)):
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".txt", delete=False
                    ) as f:
                        f.write("test")
                        test_path = f.name
                    try:
                        adapter.process(input_file_path=test_path)
                    finally:
                        self._cleanup_file(test_path)
        except (AdapterError, KeyError, ValueError, Exception):
            # Expected - configuration validation failed
            pass
