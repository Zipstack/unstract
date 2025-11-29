"""Vibe Extractor Generator.

This module generates document extraction metadata, fields, and prompts
using LLM-based agents, similar to the new_document_type_generator.py reference.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .constants import VibeExtractorBootstrapPrompts
from .llm_helper import generate_with_llm, get_llm_client

logger = logging.getLogger(__name__)


class VibeExtractorGenerator:
    """Generator for document extraction components using LLM."""

    def __init__(self, llm_config: dict[str, Any]):
        """Initialize the generator with LLM configuration.

        Args:
            llm_config: Configuration dictionary for LLM client
                - adapter_id: Provider (openai, anthropic, bedrock, etc.)
                - model: Model name
                - api_key: API key
                - temperature: Temperature (default: 0.7)
                - max_tokens: Max tokens (default: 4096)
        """
        self.llm_config = llm_config
        self.llm_client = None

    def _ensure_llm_client(self):
        """Ensure LLM client is initialized."""
        if self.llm_client is None:
            self.llm_client = get_llm_client(self.llm_config)

    def _clean_llm_response(self, response_text: str) -> str:
        """Remove code block markers from LLM response.

        Args:
            response_text: Raw response from LLM

        Returns:
            Cleaned response text
        """
        response_text = response_text.strip()

        # Remove markdown code blocks
        if response_text.startswith("```markdown"):
            response_text = response_text[11:]
        elif response_text.startswith("```yaml"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]

        if response_text.endswith("```"):
            response_text = response_text[:-3]

        return response_text.strip()

    async def generate_metadata(
        self, doc_type: str, reference_template: str
    ) -> dict[str, Any]:
        """Generate metadata for a document type using LLM.

        Args:
            doc_type: Document type name (e.g., "invoice", "receipt")
            reference_template: Reference metadata.yaml template content

        Returns:
            Dictionary containing generated metadata

        Raises:
            Exception: If metadata generation fails
        """
        self._ensure_llm_client()
        logger.info(f"Generating metadata for '{doc_type}' using LLM...")

        prompt = VibeExtractorBootstrapPrompts.DOCUMENT_METADATA.format(
            doc_type=doc_type, reference_template=reference_template
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=1000)

            # Clean and parse YAML response
            yaml_content = self._clean_llm_response(response)
            metadata = yaml.safe_load(yaml_content)

            logger.info(f"Successfully generated metadata for '{doc_type}'")
            return metadata

        except Exception as e:
            error_msg = f"Error generating metadata: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_extraction_fields(
        self, doc_type: str, metadata: dict[str, Any]
    ) -> str:
        """Generate extraction.yaml structure using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary

        Returns:
            YAML string defining extraction fields

        Raises:
            Exception: If extraction fields generation fails
        """
        self._ensure_llm_client()
        logger.info(f"Generating extraction fields for '{doc_type}' using LLM...")

        metadata_description = metadata.get("description", "")
        prompt = VibeExtractorBootstrapPrompts.DOCUMENT_EXTRACTION_FIELDS.format(
            doc_type=doc_type, metadata_description=metadata_description
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=2000)

            # Clean YAML response
            yaml_content = self._clean_llm_response(response)

            logger.info(f"Successfully generated extraction fields for '{doc_type}'")
            return yaml_content

        except Exception as e:
            error_msg = f"Error generating extraction fields: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_page_extraction_system_prompt(
        self, doc_type: str, metadata: dict[str, Any]
    ) -> str:
        """Generate page extraction system prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary

        Returns:
            System prompt text for page extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating page extraction system prompt for '{doc_type}' using LLM..."
        )

        metadata_description = metadata.get("description", "")
        prompt = VibeExtractorBootstrapPrompts.PAGE_EXTRACTION_SYSTEM.format(
            doc_type=doc_type, metadata_description=metadata_description
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=1500)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated page extraction system prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating page extraction system prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_page_extraction_user_prompt(
        self, doc_type: str, metadata: dict[str, Any]
    ) -> str:
        """Generate page extraction user prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary

        Returns:
            User prompt text for page extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating page extraction user prompt for '{doc_type}' using LLM..."
        )

        metadata_description = metadata.get("description", "")
        prompt = VibeExtractorBootstrapPrompts.PAGE_EXTRACTION_USER.format(
            doc_type=doc_type, metadata_description=metadata_description
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=500)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated page extraction user prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating page extraction user prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_scalar_extraction_system_prompt(
        self, doc_type: str, metadata: dict[str, Any], extraction_yaml: str
    ) -> str:
        """Generate scalar extraction system prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary
            extraction_yaml: Generated extraction YAML content

        Returns:
            System prompt text for scalar extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating scalar extraction system prompt for '{doc_type}' using LLM..."
        )

        # Parse extraction YAML to get scalar fields
        try:
            extraction_data = yaml.safe_load(extraction_yaml)
            scalar_fields = []
            for key, value in extraction_data.items():
                if not isinstance(value, list):
                    scalar_fields.append(key)
        except Exception:
            scalar_fields = []

        metadata_description = metadata.get("description", "")
        scalar_fields_str = ", ".join(scalar_fields[:5])

        prompt = VibeExtractorBootstrapPrompts.SCALARS_EXTRACTION_SYSTEM.format(
            doc_type=doc_type,
            metadata_description=metadata_description,
            scalar_fields=scalar_fields_str,
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=1500)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated scalar extraction system prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating scalar extraction system prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_scalar_extraction_user_prompt(
        self, doc_type: str, metadata: dict[str, Any]
    ) -> str:
        """Generate scalar extraction user prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary

        Returns:
            User prompt text for scalar extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating scalar extraction user prompt for '{doc_type}' using LLM..."
        )

        prompt = VibeExtractorBootstrapPrompts.SCALARS_EXTRACTION_USER.format(
            doc_type=doc_type
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=500)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated scalar extraction user prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating scalar extraction user prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_table_extraction_system_prompt(
        self, doc_type: str, metadata: dict[str, Any], extraction_yaml: str
    ) -> str:
        """Generate table extraction system prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary
            extraction_yaml: Generated extraction YAML content

        Returns:
            System prompt text for table extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating table extraction system prompt for '{doc_type}' using LLM..."
        )

        metadata_description = metadata.get("description", "")
        prompt = VibeExtractorBootstrapPrompts.TABLES_EXTRACTION_SYSTEM.format(
            doc_type=doc_type, metadata_description=metadata_description
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=2000)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated table extraction system prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating table extraction system prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    async def generate_table_extraction_user_prompt(
        self, doc_type: str, metadata: dict[str, Any]
    ) -> str:
        """Generate table extraction user prompt using LLM.

        Args:
            doc_type: Document type name
            metadata: Generated metadata dictionary

        Returns:
            User prompt text for table extraction

        Raises:
            Exception: If prompt generation fails
        """
        self._ensure_llm_client()
        logger.info(
            f"Generating table extraction user prompt for '{doc_type}' using LLM..."
        )

        prompt = VibeExtractorBootstrapPrompts.TABLES_EXTRACTION_USER.format(
            doc_type=doc_type
        )

        try:
            response = await generate_with_llm(self.llm_client, prompt, max_tokens=500)

            cleaned_response = self._clean_llm_response(response)
            logger.info(
                f"Successfully generated table extraction user prompt for '{doc_type}'"
            )
            return cleaned_response

        except Exception as e:
            error_msg = f"Error generating table extraction user prompt: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def save_metadata_yaml(self, output_path: Path, metadata: dict[str, Any]) -> Path:
        """Save metadata as YAML file.

        Args:
            output_path: Output directory path
            metadata: Metadata dictionary to save

        Returns:
            Path to saved metadata.yaml file
        """
        # Add default values if not present
        if "version" not in metadata:
            metadata["version"] = "1.0.0"
        if "author" not in metadata:
            metadata["author"] = "Zipstack Inc"
        if "release_date" not in metadata:
            metadata["release_date"] = "2025-07-01"
        if "price_multiplier" not in metadata:
            metadata["price_multiplier"] = 1.0
        if "llm_model" not in metadata:
            metadata["llm_model"] = "claude-sonnet-1-7"
        if "extraction_features" not in metadata:
            metadata["extraction_features"] = {
                "locate_pages": True,
                "rolling_window": False,
                "challenge": False,
            }

        metadata_file = output_path / "metadata.yaml"
        with open(metadata_file, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved metadata to {metadata_file}")
        return metadata_file

    def save_extraction_yaml(self, output_path: Path, extraction_content: str) -> Path:
        """Save extraction fields as YAML file.

        Args:
            output_path: Output directory path
            extraction_content: Extraction YAML content string

        Returns:
            Path to saved extraction.yaml file
        """
        extraction_file = output_path / "extraction.yaml"
        with open(extraction_file, "w") as f:
            f.write("---\n")
            f.write(extraction_content)
            if not extraction_content.endswith("\n"):
                f.write("\n")

        logger.info(f"Saved extraction fields to {extraction_file}")
        return extraction_file

    def save_prompt_file(self, output_path: Path, filename: str, content: str) -> Path:
        """Save prompt content to markdown file.

        Args:
            output_path: Output directory path (should include prompts subdir)
            filename: Name of the markdown file
            content: Prompt content

        Returns:
            Path to saved prompt file
        """
        prompt_file = output_path / filename
        with open(prompt_file, "w") as f:
            f.write(content)

        logger.info(f"Saved prompt to {prompt_file}")
        return prompt_file
