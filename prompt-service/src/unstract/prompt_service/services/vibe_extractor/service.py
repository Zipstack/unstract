"""Vibe Extractor Service.

This module provides the main service interface for generating
document extraction components. It orchestrates the complete
generation flow.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import VibeExtractorBootstrapPrompts
from .generator import VibeExtractorGenerator

logger = logging.getLogger(__name__)


class VibeExtractorService:
    """Service for generating document extraction components."""

    def __init__(self, llm_config: Dict[str, Any], output_dir: str):
        """Initialize the service.

        Args:
            llm_config: LLM configuration dictionary
            output_dir: Base output directory for generated files
        """
        self.generator = VibeExtractorGenerator(llm_config)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_all(
        self,
        doc_type: str,
        reference_template: str,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Generate all components for a document type.

        Args:
            doc_type: Document type name (e.g., "invoice", "receipt")
            reference_template: Reference metadata.yaml template content
            progress_callback: Optional callback to report progress

        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - output_path: Path to generated files
                - files: Dictionary of generated file paths
                - error: Error message if status is "error"
        """
        try:
            logger.info(f"Starting generation for document type: {doc_type}")

            # Create output directory for this document type
            doc_output_dir = self.output_dir / doc_type
            doc_output_dir.mkdir(parents=True, exist_ok=True)

            # Create prompts subdirectory
            prompts_dir = doc_output_dir / "prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)

            result = {
                "status": "success",
                "output_path": str(doc_output_dir),
                "files": {},
            }

            # Step 1: Generate metadata
            if progress_callback:
                progress_callback("generating_metadata", "in_progress")

            logger.info("Step 1/6: Generating metadata...")
            metadata = await self.generator.generate_metadata(
                doc_type, reference_template
            )
            metadata_file = self.generator.save_metadata_yaml(
                doc_output_dir, metadata
            )
            result["files"]["metadata"] = str(metadata_file)

            if progress_callback:
                progress_callback("generating_metadata", "completed")

            # Step 2: Generate extraction fields
            if progress_callback:
                progress_callback("generating_extraction_fields", "in_progress")

            logger.info("Step 2/6: Generating extraction fields...")
            extraction_yaml = await self.generator.generate_extraction_fields(
                doc_type, metadata
            )
            extraction_file = self.generator.save_extraction_yaml(
                doc_output_dir, extraction_yaml
            )
            result["files"]["extraction"] = str(extraction_file)

            if progress_callback:
                progress_callback("generating_extraction_fields", "completed")

            # Step 3: Generate page extraction prompts
            if progress_callback:
                progress_callback("generating_page_prompts", "in_progress")

            logger.info("Step 3/6: Generating page extraction prompts...")
            page_system_prompt = (
                await self.generator.generate_page_extraction_system_prompt(
                    doc_type, metadata
                )
            )
            page_system_file = self.generator.save_prompt_file(
                prompts_dir, "page-extraction-system.md", page_system_prompt
            )
            result["files"]["page_extraction_system"] = str(page_system_file)

            page_user_prompt = (
                await self.generator.generate_page_extraction_user_prompt(
                    doc_type, metadata
                )
            )
            page_user_file = self.generator.save_prompt_file(
                prompts_dir, "page-extraction-user.md", page_user_prompt
            )
            result["files"]["page_extraction_user"] = str(page_user_file)

            if progress_callback:
                progress_callback("generating_page_prompts", "completed")

            # Step 4: Generate scalar extraction prompts
            if progress_callback:
                progress_callback("generating_scalar_prompts", "in_progress")

            logger.info("Step 4/6: Generating scalar extraction prompts...")
            scalar_system_prompt = (
                await self.generator.generate_scalar_extraction_system_prompt(
                    doc_type, metadata, extraction_yaml
                )
            )
            scalar_system_file = self.generator.save_prompt_file(
                prompts_dir, "extraction-scalars-system.md", scalar_system_prompt
            )
            result["files"]["scalars_extraction_system"] = str(scalar_system_file)

            scalar_user_prompt = (
                await self.generator.generate_scalar_extraction_user_prompt(
                    doc_type, metadata
                )
            )
            scalar_user_file = self.generator.save_prompt_file(
                prompts_dir, "extraction-scalars-user.md", scalar_user_prompt
            )
            result["files"]["scalars_extraction_user"] = str(scalar_user_file)

            if progress_callback:
                progress_callback("generating_scalar_prompts", "completed")

            # Step 5: Generate table extraction prompts
            if progress_callback:
                progress_callback("generating_table_prompts", "in_progress")

            logger.info("Step 5/6: Generating table extraction prompts...")
            table_system_prompt = (
                await self.generator.generate_table_extraction_system_prompt(
                    doc_type, metadata, extraction_yaml
                )
            )
            table_system_file = self.generator.save_prompt_file(
                prompts_dir, "extraction-table-system.md", table_system_prompt
            )
            result["files"]["tables_extraction_system"] = str(table_system_file)

            table_user_prompt = (
                await self.generator.generate_table_extraction_user_prompt(
                    doc_type, metadata
                )
            )
            table_user_file = self.generator.save_prompt_file(
                prompts_dir, "extraction-table-user.md", table_user_prompt
            )
            result["files"]["tables_extraction_user"] = str(table_user_file)

            if progress_callback:
                progress_callback("generating_table_prompts", "completed")

            logger.info(
                f"Successfully generated all components for '{doc_type}' at {doc_output_dir}"
            )
            return result

        except Exception as e:
            error_msg = f"Error during generation: {str(e)}"
            logger.error(error_msg, exc_info=True)

            if progress_callback:
                progress_callback("error", "failed", error_msg)

            return {"status": "error", "error": error_msg}

    async def generate_metadata_only(
        self, doc_type: str, reference_template: str
    ) -> Dict[str, Any]:
        """Generate only metadata for a document type.

        Args:
            doc_type: Document type name
            reference_template: Reference metadata.yaml template

        Returns:
            Dictionary containing generated metadata or error
        """
        try:
            logger.info(f"Generating metadata for: {doc_type}")
            metadata = await self.generator.generate_metadata(
                doc_type, reference_template
            )
            return {"status": "success", "metadata": metadata}
        except Exception as e:
            error_msg = f"Error generating metadata: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}

    async def generate_extraction_fields_only(
        self, doc_type: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate only extraction fields for a document type.

        Args:
            doc_type: Document type name
            metadata: Metadata dictionary

        Returns:
            Dictionary containing extraction YAML or error
        """
        try:
            logger.info(f"Generating extraction fields for: {doc_type}")
            extraction_yaml = await self.generator.generate_extraction_fields(
                doc_type, metadata
            )
            return {"status": "success", "extraction_yaml": extraction_yaml}
        except Exception as e:
            error_msg = f"Error generating extraction fields: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}
