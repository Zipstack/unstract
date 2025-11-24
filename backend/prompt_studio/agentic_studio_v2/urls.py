"""URL routing for Agentic Studio V2."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgenticAnalyticsViewSet,
    AgenticComparisonResultViewSet,
    AgenticDocumentViewSet,
    AgenticExtractionNoteViewSet,
    AgenticExtractedDataViewSet,
    AgenticExtractionViewSet,
    AgenticLogViewSet,
    AgenticProjectViewSet,
    AgenticPromptVersionViewSet,
    AgenticSchemaViewSet,
    AgenticSettingViewSet,
    AgenticSummaryViewSet,
    AgenticTuningViewSet,
    AgenticVerifiedDataViewSet,
    connector_detail,
    connectors_list,
    pipeline_events,
)

# Create router and register viewsets
# trailing_slash=True ensures DRF URLs end with / (Django convention)
router = DefaultRouter(trailing_slash=True)

# Register model-based viewsets
router.register(r"projects", AgenticProjectViewSet, basename="agentic-project")
router.register(r"documents", AgenticDocumentViewSet, basename="agentic-document")
router.register(r"schemas", AgenticSchemaViewSet, basename="agentic-schema")
router.register(r"summaries", AgenticSummaryViewSet, basename="agentic-summary")
router.register(
    r"verified-data", AgenticVerifiedDataViewSet, basename="agentic-verified-data"
)
router.register(
    r"extracted-data", AgenticExtractedDataViewSet, basename="agentic-extracted-data"
)
router.register(
    r"comparison-results",
    AgenticComparisonResultViewSet,
    basename="agentic-comparison-result",
)
router.register(
    r"extraction-notes",
    AgenticExtractionNoteViewSet,
    basename="agentic-extraction-note",
)
router.register(
    r"prompt-versions", AgenticPromptVersionViewSet, basename="agentic-prompt-version"
)
router.register(r"settings", AgenticSettingViewSet, basename="agentic-setting")
router.register(r"logs", AgenticLogViewSet, basename="agentic-log")

# Register non-model viewsets (ViewSet, not ModelViewSet)
router.register(r"extraction", AgenticExtractionViewSet, basename="agentic-extraction")
router.register(r"tuning", AgenticTuningViewSet, basename="agentic-tuning")
router.register(r"analytics", AgenticAnalyticsViewSet, basename="agentic-analytics")

urlpatterns = [
    # Router URLs
    path("", include(router.urls)),
    # Nested routes for documents under projects (for frontend compatibility)
    # Frontend calls /projects/{project_id}/documents/{document_id}/raw-text/
    path(
        "projects/<uuid:project_pk>/documents/<uuid:pk>/raw-text/",
        AgenticDocumentViewSet.as_view({"get": "get_raw_text"}),
        name="project-documents-raw-text",
    ),
    path(
        "projects/<uuid:project_pk>/documents/<uuid:pk>/summary/",
        AgenticDocumentViewSet.as_view({"get": "get_summary"}),
        name="project-documents-summary",
    ),
    path(
        "projects/<uuid:project_pk>/documents/<uuid:pk>/verified-data/",
        AgenticDocumentViewSet.as_view({"get": "get_verified_data"}),
        name="project-documents-verified-data",
    ),
    path(
        "projects/<uuid:project_pk>/documents/<uuid:pk>/extraction-data/",
        AgenticDocumentViewSet.as_view({"get": "get_extraction_data"}),
        name="project-documents-extraction-data",
    ),
    # Generate verified data for a document
    # Frontend calls /projects/{project_id}/extract/verified/{document_id}/generate
    path(
        "projects/<uuid:project_pk>/extract/verified/<uuid:pk>/generate",
        AgenticVerifiedDataViewSet.as_view({"post": "generate_verified_data"}),
        name="project-verified-data-generate",
    ),
    # Connectors list and detail
    path("connectors/", connectors_list, name="connectors-list"),
    path("connectors/<uuid:connector_id>/", connector_detail, name="connector-detail"),
    # Server-Sent Events for real-time updates
    path("events/<uuid:project_id>/", pipeline_events, name="pipeline-events"),
    # Nested routes for prompts under projects
    # Frontend calls /projects/{project_id}/prompts/ to get prompt history or create new version
    path(
        "projects/<uuid:project_pk>/prompts/",
        AgenticPromptVersionViewSet.as_view({
            "get": "list_for_project",
            "post": "create_for_project"
        }),
        name="project-prompts-list",
    ),
    # Frontend calls /projects/{project_id}/prompts/latest to get latest prompt
    path(
        "projects/<uuid:project_pk>/prompts/latest/",
        AgenticPromptVersionViewSet.as_view({"get": "get_latest"}),
        name="project-prompts-latest",
    ),
    # Frontend calls /projects/{project_id}/prompts/{version} to get specific version
    path(
        "projects/<uuid:project_pk>/prompts/<int:version>/",
        AgenticPromptVersionViewSet.as_view({"get": "get_by_version"}),
        name="project-prompts-by-version",
    ),
    # Frontend calls /projects/{project_id}/prompts/tune
    path(
        "projects/<uuid:project_pk>/prompts/tune/",
        AgenticPromptVersionViewSet.as_view({"post": "tune_prompt"}),
        name="project-prompts-tune",
    ),
    # Frontend calls /projects/{project_id}/prompts/tune-status
    path(
        "projects/<uuid:project_pk>/prompts/tune-status/",
        AgenticPromptVersionViewSet.as_view({"get": "get_tune_status"}),
        name="project-prompts-tune-status",
    ),
    # Frontend calls /projects/{project_id}/prompts/generate-with-dependencies
    path(
        "projects/<uuid:pk>/prompts/generate-with-dependencies/",
        AgenticProjectViewSet.as_view({"post": "generate_prompt_with_dependencies"}),
        name="project-prompts-generate-with-deps",
    ),
    # Data retrieval endpoints for frontend tabs
    path(
        "projects/<uuid:project_pk>/processing/documents/<uuid:document_id>/extracted-data/",
        AgenticProjectViewSet.as_view({"get": "get_document_extracted_data"}),
        name="project-document-extracted-data",
    ),
    path(
        "projects/<uuid:project_pk>/extract/verified/<uuid:document_id>/",
        AgenticProjectViewSet.as_view({"get": "get_document_verified_data"}),
        name="project-document-verified-data",
    ),
    path(
        "projects/<uuid:project_pk>/extract/verified/<uuid:document_id>/promote/",
        AgenticProjectViewSet.as_view({"post": "promote_to_verified"}),
        name="project-promote-to-verified",
    ),
    # Document comparison endpoint
    path(
        "projects/<uuid:pk>/documents/<uuid:document_id>/comparison/",
        AgenticProjectViewSet.as_view({"get": "get_document_comparison"}),
        name="project-document-comparison",
    ),
]
