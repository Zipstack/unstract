"""Helper functions for Vibe Extractor operations."""

from pathlib import Path
from typing import Any

import yaml
from django.conf import settings

from prompt_studio.prompt_studio_vibe_extractor_v2.constants import (
    VibeExtractorFileNames,
    VibeExtractorPaths,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.exceptions import (
    FileReadError,
    InvalidDocumentTypeError,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)


class VibeExtractorHelper:
    """Helper class for Vibe Extractor operations."""

    @staticmethod
    def validate_document_type(doc_type: str) -> str:
        """Validate and normalize document type name.

        Args:
            doc_type: Document type name

        Returns:
            Normalized document type (lowercase with hyphens)

        Raises:
            InvalidDocumentTypeError: If document type is invalid
        """
        if not doc_type or not doc_type.strip():
            raise InvalidDocumentTypeError("Document type cannot be empty")

        # Convert to lowercase and replace spaces with hyphens
        normalized = doc_type.lower().replace(" ", "-").replace("_", "-")

        # Remove special characters except hyphens
        normalized = "".join(c for c in normalized if c.isalnum() or c == "-")

        if not normalized:
            raise InvalidDocumentTypeError(f"Invalid document type: {doc_type}")

        return normalized

    @staticmethod
    def get_project_output_path(project: VibeExtractorProject) -> Path:
        """Get the output path for a project.

        Args:
            project: VibeExtractorProject instance

        Returns:
            Path object for the project output directory
        """
        if project.generation_output_path:
            return Path(project.generation_output_path)

        # Default to staging directory
        base_dir = getattr(
            settings,
            "VIBE_EXTRACTOR_OUTPUT_DIR",
            Path(settings.BASE_DIR).parent / VibeExtractorPaths.STAGING_DIR,
        )
        normalized_type = VibeExtractorHelper.validate_document_type(
            project.document_type
        )
        return Path(base_dir) / normalized_type

    @staticmethod
    def ensure_output_directory(project: VibeExtractorProject) -> Path:
        """Ensure output directory exists for a project.

        Args:
            project: VibeExtractorProject instance

        Returns:
            Path object for the created directory
        """
        output_path = VibeExtractorHelper.get_project_output_path(project)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create prompts subdirectory
        prompts_path = output_path / VibeExtractorPaths.PROMPTS_DIR
        prompts_path.mkdir(parents=True, exist_ok=True)

        return output_path

    @staticmethod
    def read_generated_file(project: VibeExtractorProject, file_type: str) -> str:
        """Read a generated file for a project.

        Args:
            project: VibeExtractorProject instance
            file_type: Type of file to read

        Returns:
            Content of the file

        Raises:
            FileReadError: If file cannot be read
        """
        output_path = VibeExtractorHelper.get_project_output_path(project)

        file_map = {
            "metadata": output_path / VibeExtractorFileNames.METADATA_YAML,
            "extraction": output_path / VibeExtractorFileNames.EXTRACTION_YAML,
            "page_extraction_system": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.PAGE_EXTRACTION_SYSTEM_MD,
            "page_extraction_user": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.PAGE_EXTRACTION_USER_MD,
            "scalars_extraction_system": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.SCALARS_EXTRACTION_SYSTEM_MD,
            "scalars_extraction_user": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.SCALARS_EXTRACTION_USER_MD,
            "tables_extraction_system": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.TABLES_EXTRACTION_SYSTEM_MD,
            "tables_extraction_user": output_path
            / VibeExtractorPaths.PROMPTS_DIR
            / VibeExtractorFileNames.TABLES_EXTRACTION_USER_MD,
        }

        file_path = file_map.get(file_type)
        if not file_path:
            raise FileReadError(f"Unknown file type: {file_type}")

        if not file_path.exists():
            raise FileReadError(f"File not found: {file_path}. Generate the files first.")

        try:
            with open(file_path) as f:
                return f.read()
        except Exception as e:
            raise FileReadError(f"Error reading file {file_path}: {str(e)}") from e

    @staticmethod
    def update_generation_progress(
        project: VibeExtractorProject,
        step: str,
        status: str,
        message: str | None = None,
    ) -> None:
        """Update generation progress for a project.

        Args:
            project: VibeExtractorProject instance
            step: Generation step name
            status: Status of the step (pending, in_progress, completed, failed)
            message: Optional message
        """
        if not project.generation_progress:
            project.generation_progress = {}

        project.generation_progress[step] = {
            "status": status,
            "message": message or "",
        }
        project.save(update_fields=["generation_progress", "modified_at"])

    @staticmethod
    def get_reference_template(template_name: str) -> str:
        """Get reference template content.

        Args:
            template_name: Name of the template file

        Returns:
            Content of the reference template

        Raises:
            FileReadError: If template cannot be read
        """
        reference_dir = getattr(
            settings,
            "VIBE_EXTRACTOR_REFERENCE_DIR",
            Path(settings.BASE_DIR).parent / VibeExtractorPaths.REFERENCE_DIR,
        )
        template_path = Path(reference_dir) / template_name

        if not template_path.exists():
            raise FileReadError(f"Reference template not found: {template_path}")

        try:
            with open(template_path) as f:
                return f.read()
        except Exception as e:
            raise FileReadError(
                f"Error reading reference template {template_path}: {str(e)}"
            ) from e

    @staticmethod
    def save_yaml_file(output_path: Path, filename: str, content: dict[str, Any]) -> None:
        """Save content as YAML file.

        Args:
            output_path: Output directory path
            filename: Name of the file
            content: Content to save as YAML
        """
        file_path = output_path / filename
        with open(file_path, "w") as f:
            yaml.dump(content, f, default_flow_style=False, sort_keys=False)

    @staticmethod
    def save_markdown_file(output_path: Path, filename: str, content: str) -> None:
        """Save content as markdown file.

        Args:
            output_path: Output directory path
            filename: Name of the file
            content: Content to save
        """
        file_path = output_path / filename
        with open(file_path, "w") as f:
            f.write(content)
