"""API Helper for Vibe Extractor.

This module provides helper functions for backend API integration.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .service import VibeExtractorService

logger = logging.getLogger(__name__)


async def generate_document_extraction_components(
    doc_type: str,
    output_dir: str,
    llm_config: Dict[str, Any],
    reference_template: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> Dict[str, Any]:
    """Generate all document extraction components.

    This is the main entry point for backend API to trigger generation.

    Args:
        doc_type: Document type name (e.g., "invoice", "receipt")
        output_dir: Base output directory for generated files
        llm_config: LLM configuration dictionary containing:
            - adapter_id: Provider (openai, anthropic, bedrock, azureopenai)
            - model: Model name
            - api_key: API key
            - temperature: Temperature (default: 0.7)
            - max_tokens: Max tokens (default: 4096)
        reference_template: Optional reference metadata.yaml template content.
            If not provided, a default template will be used.
        progress_callback: Optional callback function(step, status, message)
            to report generation progress

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - output_path: Path to generated files
            - files: Dictionary of generated file paths
            - error: Error message if status is "error"

    Example:
        ```python
        llm_config = {
            "adapter_id": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "sk-ant-...",
            "temperature": 0.7,
            "max_tokens": 4096
        }

        result = await generate_document_extraction_components(
            doc_type="invoice",
            output_dir="/path/to/output",
            llm_config=llm_config
        )

        if result["status"] == "success":
            print(f"Generated files at: {result['output_path']}")
            print(f"Files: {result['files']}")
        else:
            print(f"Error: {result['error']}")
        ```
    """
    try:
        # Use default reference template if not provided
        if reference_template is None:
            reference_template = _get_default_reference_template()

        # Initialize service
        service = VibeExtractorService(llm_config, output_dir)

        # Generate all components
        result = await service.generate_all(
            doc_type, reference_template, progress_callback
        )

        return result

    except Exception as e:
        error_msg = f"Error in generate_document_extraction_components: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "error": error_msg}


async def generate_metadata_only(
    doc_type: str,
    llm_config: Dict[str, Any],
    reference_template: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate only metadata for a document type.

    Args:
        doc_type: Document type name
        llm_config: LLM configuration dictionary
        reference_template: Optional reference template

    Returns:
        Dictionary containing generated metadata or error
    """
    try:
        if reference_template is None:
            reference_template = _get_default_reference_template()

        # Initialize service with temporary output dir
        service = VibeExtractorService(llm_config, "/tmp/vibe_extractor")

        result = await service.generate_metadata_only(doc_type, reference_template)
        return result

    except Exception as e:
        error_msg = f"Error generating metadata: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


async def generate_extraction_fields_only(
    doc_type: str,
    metadata: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate only extraction fields for a document type.

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing extraction YAML or error
    """
    try:
        # Initialize service with temporary output dir
        service = VibeExtractorService(llm_config, "/tmp/vibe_extractor")

        result = await service.generate_extraction_fields_only(doc_type, metadata)
        return result

    except Exception as e:
        error_msg = f"Error generating extraction fields: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


def _get_default_reference_template() -> str:
    """Get default reference metadata.yaml template.

    Returns:
        Default reference template as string
    """
    return """---
name_identifier: example  # Unique identifier
name: Example Document  # Human-readable name
description: |  # Description of the document type
  Example document description.
  This should be 3-4 sentences explaining what this document type is.
description_seo: |  # SEO optimized description
  SEO optimized description for example document.
html_meta_description: |  # HTML meta description
  HTML meta description for example document.
tags:  # List of tags
  - example
  - document
  - sample
version: 1.0.0  # Version
status: beta  # Current status
visibility: public  # Visibility
author: Zipstack Inc  # Author
release_date: 2025-07-01  # Release date
price_multiplier: 1.0  # Price multiplier
llm_model: claude-sonnet-1-7  # LLM model
extraction_features:  # Extraction features
  locate_pages: true
  rolling_window: false
  challenge: false
"""


def validate_llm_config(llm_config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate LLM configuration.

    Args:
        llm_config: LLM configuration dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["adapter_id", "model", "api_key"]

    for field in required_fields:
        if field not in llm_config:
            return False, f"Missing required field: {field}"

    valid_adapters = ["openai", "azureopenai", "anthropic", "bedrock"]
    if llm_config["adapter_id"] not in valid_adapters:
        return (
            False,
            f"Invalid adapter_id: {llm_config['adapter_id']}. "
            f"Must be one of: {', '.join(valid_adapters)}",
        )

    return True, None
