from django.urls import path
from rest_framework.routers import SimpleRouter

from prompt_studio.prompt_studio_vibe_extractor_v2.views import (
    VibeExtractorProjectView,
)

# Create router for standard CRUD operations
router = SimpleRouter()
router.register(
    r"vibe-extractor",
    VibeExtractorProjectView,
    basename="vibe-extractor",
)

# Get viewset instance for custom actions
viewset = VibeExtractorProjectView.as_view

# Explicit URL patterns for generation endpoints
generation_patterns = [
    # Generate all components at once
    path(
        "vibe-extractor/<str:pk>/generate/",
        viewset({"post": "generate"}),
        name="vibe-extractor-generate",
    ),
    # Generate metadata only
    path(
        "vibe-extractor/<str:pk>/generate-metadata/",
        viewset({"post": "generate_metadata"}),
        name="vibe-extractor-generate-metadata",
    ),
    # Generate extraction fields
    path(
        "vibe-extractor/<str:pk>/generate-extraction-fields/",
        viewset({"post": "generate_extraction_fields"}),
        name="vibe-extractor-generate-extraction-fields",
    ),
    # Generate page extraction prompts
    path(
        "vibe-extractor/<str:pk>/generate-page-prompts/",
        viewset({"post": "generate_page_prompts"}),
        name="vibe-extractor-generate-page-prompts",
    ),
    # Generate scalar extraction prompts
    path(
        "vibe-extractor/<str:pk>/generate-scalar-prompts/",
        viewset({"post": "generate_scalar_prompts"}),
        name="vibe-extractor-generate-scalar-prompts",
    ),
    # Generate table extraction prompts
    path(
        "vibe-extractor/<str:pk>/generate-table-prompts/",
        viewset({"post": "generate_table_prompts"}),
        name="vibe-extractor-generate-table-prompts",
    ),
    # Read generated file
    path(
        "vibe-extractor/<str:pk>/read-file/",
        viewset({"get": "read_file"}),
        name="vibe-extractor-read-file",
    ),
    # List generated files
    path(
        "vibe-extractor/<str:pk>/list-files/",
        viewset({"get": "list_files"}),
        name="vibe-extractor-list-files",
    ),
    # Guess document type from file
    path(
        "vibe-extractor/guess-document-type/",
        viewset({"post": "guess_document_type"}),
        name="vibe-extractor-guess-document-type",
    ),
]

# Combine router URLs with explicit generation patterns
urlpatterns = router.urls + generation_patterns
