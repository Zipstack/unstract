"""Helper functions for Vibe Extractor operations."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from utils.file_storage.helpers.prompt_studio_file_helper import (
    PromptStudioFileHelper,
)

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

logger = logging.getLogger(__name__)


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

    @staticmethod
    def guess_document_type_from_file(
        file_name: str,
        tool_id: str,
        org_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Guess document type from file content.

        This method:
        1. Constructs the file path using permanent file storage
        2. Reads the file content using dynamic_extractor
        3. Calls prompt-service to guess the document type using LLM

        Args:
            file_name: Name of the file in permanent storage
            tool_id: Tool ID to construct the file path
            org_id: Organization ID
            user_id: User ID

        Returns:
            Dictionary containing:
                - status: "success" or "error"
                - document_type: Guessed document type (if success)
                - confidence: Confidence score (if applicable)
                - error: Error message (if error)
        """
        try:
            # Import here to avoid circular imports
            from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import (
                PromptStudioHelper,
            )
            from prompt_studio.prompt_studio_vibe_extractor_v2.services.generator_service import (
                GeneratorService,
            )
            from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
            from prompt_studio.prompt_studio_core_v2.models import CustomTool

            # Get the tool instance to access profile manager
            tool = CustomTool.objects.get(pk=tool_id)

            # Get default profile for extraction
            default_profile = ProfileManager.get_default_llm_profile(tool)

            # Construct file path using PromptStudioFileHelper
            file_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                org_id=org_id,
                user_id=user_id,
                tool_id=tool_id,
                is_create=False,
            )
            full_file_path = str(Path(file_path) / file_name)

            # Use dynamic_extractor to read and extract text from the file
            from unstract.sdk1.file_storage.env_helper import EnvHelper
            from unstract.sdk1.file_storage.constants import StorageType
            from utils.file_storage.constants import FileStorageKeys
            from unstract.sdk1.utils.indexing import IndexingUtils
            from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import PromptIdeBaseTool
            from unstract.sdk.constants import LogLevel

            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
            util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

            # Generate doc_id for extraction
            doc_id = IndexingUtils.generate_index_key(
                vector_db=str(default_profile.vector_store.id),
                embedding=str(default_profile.embedding_model.id),
                x2text=str(default_profile.x2text.id),
                chunk_size=str(default_profile.chunk_size),
                chunk_overlap=str(default_profile.chunk_overlap),
                file_path=full_file_path,
                file_hash=None,
                fs=fs_instance,
                tool=util,
            )

            # Extract text from the file
            extracted_text = PromptStudioHelper.dynamic_extractor(
                profile_manager=default_profile,
                file_path=full_file_path,
                org_id=org_id,
                document_id=None,  # Not needed for this operation
                run_id=None,
                enable_highlight=False,
                doc_id=doc_id,
            )

            if not extracted_text or not extracted_text.strip():
                return {
                    "status": "error",
                    "error": "Could not extract text from file",
                }

            # Get LLM configuration from system LLM
            llm_config = GeneratorService._get_llm_config()

            # Call prompt-service via SDK helper
            from prompt_studio.prompt_studio_vibe_extractor_v2.services.prompt_service_helper import (
                VibeExtractorPromptServiceHelper,
            )

            result = VibeExtractorPromptServiceHelper.guess_document_type(
                file_content=extracted_text,
                llm_config=llm_config,
                org_id=org_id,
            )

            return result

        except Exception as e:
            logger.error(f"Error guessing document type: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }
