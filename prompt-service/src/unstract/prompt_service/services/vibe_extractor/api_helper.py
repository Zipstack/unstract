"""API Helper for Vibe Extractor.

This module provides helper functions for backend API integration.
"""

import asyncio
import logging
from typing import Any

from .service import VibeExtractorService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async coroutines in sync context.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
            return result
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        return result


def generate_document_extraction_components_sync(
    doc_type: str,
    output_dir: str,
    llm_config: Dict[str, Any],
    reference_template: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> Dict[str, Any]:
    """Generate all document extraction components (sync version).

    This is the main entry point for backend API to trigger generation.

    Args:
        doc_type: Document type name (e.g., "invoice", "receipt")
        output_dir: Base output directory for generated files
        llm_config: LLM configuration dictionary
        reference_template: Optional reference metadata.yaml template content
        progress_callback: Optional callback function(step, status, message)

    Returns:
        Dictionary containing generation result
    """
    return _run_async(
        generate_document_extraction_components_async(
            doc_type, output_dir, llm_config, reference_template, progress_callback
        )
    )


async def generate_document_extraction_components_async(
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
            "max_tokens": 4096,
        }

        result = await generate_document_extraction_components(
            doc_type="invoice", output_dir="/path/to/output", llm_config=llm_config
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


def generate_metadata_only_sync(
    doc_type: str,
    llm_config: Dict[str, Any],
    reference_template: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate only metadata for a document type (sync version).

    Args:
        doc_type: Document type name
        llm_config: LLM configuration dictionary
        reference_template: Optional reference template

    Returns:
        Dictionary containing generated metadata or error
    """
    return _run_async(
        generate_metadata_only_async(doc_type, llm_config, reference_template)
    )


async def generate_metadata_only_async(
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


def generate_extraction_fields_only_sync(
    doc_type: str,
    metadata: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate only extraction fields for a document type (sync version).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing extraction YAML or error
    """
    return _run_async(
        generate_extraction_fields_only_async(doc_type, metadata, llm_config)
    )


async def generate_extraction_fields_only_async(
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


def generate_page_extraction_prompts_sync(
    doc_type: str,
    metadata: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate page extraction prompts (sync version).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    return _run_async(
        generate_page_extraction_prompts_async(doc_type, metadata, llm_config)
    )


async def generate_page_extraction_prompts_async(
    doc_type: str,
    metadata: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate page extraction prompts (system and user).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    try:
        # Initialize service with temporary output dir
        service = VibeExtractorService(llm_config, "/tmp/vibe_extractor")

        # Generate both prompts
        page_system_prompt = (
            await service.generator.generate_page_extraction_system_prompt(
                doc_type, metadata
            )
        )
        page_user_prompt = await service.generator.generate_page_extraction_user_prompt(
            doc_type, metadata
        )

        return {
            "status": "success",
            "system_prompt": page_system_prompt,
            "user_prompt": page_user_prompt,
        }

    except Exception as e:
        error_msg = f"Error generating page extraction prompts: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


def generate_scalar_extraction_prompts_sync(
    doc_type: str,
    metadata: Dict[str, Any],
    extraction_yaml: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate scalar extraction prompts (sync version).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        extraction_yaml: Extraction YAML content
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    return _run_async(
        generate_scalar_extraction_prompts_async(
            doc_type, metadata, extraction_yaml, llm_config
        )
    )


async def generate_scalar_extraction_prompts_async(
    doc_type: str,
    metadata: Dict[str, Any],
    extraction_yaml: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate scalar extraction prompts (system and user).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        extraction_yaml: Extraction YAML content
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    try:
        # Initialize service with temporary output dir
        service = VibeExtractorService(llm_config, "/tmp/vibe_extractor")

        # Generate both prompts
        scalar_system_prompt = (
            await service.generator.generate_scalar_extraction_system_prompt(
                doc_type, metadata, extraction_yaml
            )
        )
        scalar_user_prompt = (
            await service.generator.generate_scalar_extraction_user_prompt(
                doc_type, metadata
            )
        )

        return {
            "status": "success",
            "system_prompt": scalar_system_prompt,
            "user_prompt": scalar_user_prompt,
        }

    except Exception as e:
        error_msg = f"Error generating scalar extraction prompts: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


def generate_table_extraction_prompts_sync(
    doc_type: str,
    metadata: Dict[str, Any],
    extraction_yaml: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate table extraction prompts (sync version).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        extraction_yaml: Extraction YAML content
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    return _run_async(
        generate_table_extraction_prompts_async(
            doc_type, metadata, extraction_yaml, llm_config
        )
    )


async def generate_table_extraction_prompts_async(
    doc_type: str,
    metadata: Dict[str, Any],
    extraction_yaml: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate table extraction prompts (system and user).

    Args:
        doc_type: Document type name
        metadata: Metadata dictionary
        extraction_yaml: Extraction YAML content
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing system and user prompts or error
    """
    try:
        # Initialize service with temporary output dir
        service = VibeExtractorService(llm_config, "/tmp/vibe_extractor")

        # Generate both prompts
        table_system_prompt = (
            await service.generator.generate_table_extraction_system_prompt(
                doc_type, metadata, extraction_yaml
            )
        )
        table_user_prompt = (
            await service.generator.generate_table_extraction_user_prompt(
                doc_type, metadata
            )
        )

        return {
            "status": "success",
            "system_prompt": table_system_prompt,
            "user_prompt": table_user_prompt,
        }

    except Exception as e:
        error_msg = f"Error generating table extraction prompts: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


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


def guess_document_type_sync(
    file_content: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Guess document type from file content (sync version).

    Args:
        file_content: Extracted text content from the document
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing guessed document type or error
    """
    return _run_async(
        guess_document_type_async(file_content, llm_config)
    )


async def guess_document_type_async(
    file_content: str,
    llm_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Guess document type from file content using LLM.

    Args:
        file_content: Extracted text content from the document
        llm_config: LLM configuration dictionary

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - document_type: Guessed document type (if success)
            - confidence: Confidence description (if applicable)
            - error: Error message (if error)
    """
    try:
        # Validate LLM config
        is_valid, error_msg = validate_llm_config(llm_config)
        if not is_valid:
            return {"status": "error", "error": error_msg}

        # Import LLM helper
        from .llm_helper import guess_document_type_with_llm

        # Call LLM helper to guess document type
        result = await guess_document_type_with_llm(
            file_content=file_content,
            llm_config=llm_config,
        )

        return result

    except Exception as e:
        error_msg = f"Error guessing document type: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "error": error_msg}
