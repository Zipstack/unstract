"""Constants for Vibe Extractor."""


class VibeExtractorKeys:
    """Keys for Vibe Extractor API requests and responses."""

    PROJECT_ID = "project_id"
    DOCUMENT_TYPE = "document_type"
    STATUS = "status"
    GENERATION_OUTPUT_PATH = "generation_output_path"
    ERROR_MESSAGE = "error_message"
    GENERATION_PROGRESS = "generation_progress"
    TOOL_ID = "tool_id"


class VibeExtractorFileNames:
    """File names for generated files."""

    METADATA_YAML = "metadata.yaml"
    EXTRACTION_YAML = "extraction.yaml"
    PAGE_EXTRACTION_SYSTEM_MD = "page-extraction-system.md"
    PAGE_EXTRACTION_USER_MD = "page-extraction-user.md"
    SCALARS_EXTRACTION_SYSTEM_MD = "extraction-scalars-system.md"
    SCALARS_EXTRACTION_USER_MD = "extraction-scalars-user.md"
    TABLES_EXTRACTION_SYSTEM_MD = "extraction-table-system.md"
    TABLES_EXTRACTION_USER_MD = "extraction-table-user.md"


class VibeExtractorPaths:
    """Path constants for Vibe Extractor."""

    PROMPTS_DIR = "prompts"
    STAGING_DIR = "staging"
    REFERENCE_DIR = "reference"


class GenerationSteps:
    """Steps in the generation process."""

    METADATA = "metadata"
    EXTRACTION_FIELDS = "extraction_fields"
    PAGE_EXTRACTION_PROMPTS = "page_extraction_prompts"
    SCALARS_EXTRACTION_PROMPTS = "scalars_extraction_prompts"
    TABLES_EXTRACTION_PROMPTS = "tables_extraction_prompts"
