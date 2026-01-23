"""Django REST Framework views for Look-Up API.

This module provides RESTful API endpoints for managing Look-Up projects,
templates, reference data, and executing Look-Ups.
"""

import logging
import uuid

from account_v2.custom_exceptions import DuplicateData
from django.db import IntegrityError, transaction
from permissions.permission import IsOwner
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper
from utils.pagination import CustomPagination

from .constants import LookupProfileManagerErrors, LookupProfileManagerKeys
from .exceptions import ExtractionNotCompleteError
from .models import (
    LookupDataSource,
    LookupExecutionAudit,
    LookupProfileManager,
    LookupProject,
    LookupPromptTemplate,
    PromptStudioLookupLink,
)
from .serializers import (
    BulkLinkSerializer,
    LookupDataSourceSerializer,
    LookupExecutionAuditSerializer,
    LookupExecutionRequestSerializer,
    LookupExecutionResponseSerializer,
    LookupProfileManagerSerializer,
    LookupProjectSerializer,
    LookupPromptTemplateSerializer,
    PromptStudioLookupLinkSerializer,
    ReferenceDataUploadSerializer,
    TemplateValidationSerializer,
)
from .services import (
    AuditLogger,
    EnrichmentMerger,
    LLMResponseCache,
    LookUpExecutor,
    LookUpOrchestrator,
    ReferenceDataLoader,
    VariableResolver,
)

logger = logging.getLogger(__name__)


class LookupProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Look-Up projects.

    Provides CRUD operations and additional actions for
    executing Look-Ups and managing reference data.
    """

    queryset = LookupProject.objects.all()
    serializer_class = LookupProjectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        """Filter projects by organization and active status."""
        # Note: Organization filtering is handled automatically by
        # DefaultOrganizationMixin's save() method and queryset filtering
        # should be handled by a custom manager if needed (like Prompt Studio)
        queryset = super().get_queryset()

        # Filter by active status if requested
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset.select_related("template")

    def perform_create(self, serializer):
        """Set created_by from request."""
        # Note: organization is set automatically by DefaultOrganizationMixin's save() method
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Delete a Look-Up project.

        Prevents deletion if the project is linked to any Prompt Studio projects.
        """
        instance = self.get_object()

        # Check if the project is linked to any Prompt Studio projects
        linked_ps_projects = instance.ps_links.all()
        if linked_ps_projects.exists():
            # Get linked project IDs for the error message
            linked_ids = list(
                linked_ps_projects.values_list("prompt_studio_project_id", flat=True)
            )
            return Response(
                {
                    "error": "Cannot delete Look-Up project that is linked to "
                    "Prompt Studio projects",
                    "detail": f"This Look-Up project is linked to {len(linked_ids)} "
                    f"Prompt Studio project(s). Please unlink it from all Prompt "
                    f"Studio projects before deleting.",
                    "linked_prompt_studio_projects": [str(id) for id in linked_ids],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Proceed with deletion
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Execute a Look-Up project with provided input data.

        POST /api/v1/lookup-projects/{id}/execute/
        """
        project = self.get_object()

        # Validate request
        request_serializer = LookupExecutionRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        input_data = request_serializer.validated_data["input_data"]
        use_cache = request_serializer.validated_data["use_cache"]
        timeout = request_serializer.validated_data["timeout_seconds"]

        try:
            # Get the LLM adapter from Lookup profile
            from utils.user_context import UserContext

            from .integrations.file_storage_client import FileStorageClient
            from .integrations.unstract_llm_client import UnstractLLMClient

            # Get organization ID for RAG retrieval (must match what was used during indexing)
            org_id = UserContext.get_organization_identifier()

            # Get profile for this project
            profile = LookupProfileManager.objects.filter(lookup_project=project).first()

            if not profile or not profile.llm:
                return Response(
                    {"error": "No LLM profile configured for this Look-Up project"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create real LLM client using the profile's adapter
            llm_client = UnstractLLMClient(profile.llm)
            storage_client = FileStorageClient()
            cache = LLMResponseCache() if use_cache else None
            ref_loader = ReferenceDataLoader(storage_client)
            merger = EnrichmentMerger()

            executor = LookUpExecutor(
                variable_resolver=VariableResolver,
                cache_manager=cache,
                reference_loader=ref_loader,
                llm_client=llm_client,
                org_id=org_id,
            )

            orchestrator = LookUpOrchestrator(
                executor=executor,
                merger=merger,
                config={"execution_timeout_seconds": timeout},
            )

            # Execute Look-Up
            result = orchestrator.execute_lookups(
                input_data=input_data, lookup_projects=[project]
            )

            # Check if any lookups failed - return error response if so
            metadata = result.get("_lookup_metadata", {})
            enrichments = metadata.get("enrichments", [])
            failed_enrichments = [e for e in enrichments if e.get("status") == "failed"]

            if failed_enrichments:
                # Find context window errors first (more specific)
                context_window_error = next(
                    (
                        e
                        for e in failed_enrichments
                        if e.get("error_type") == "context_window_exceeded"
                    ),
                    None,
                )

                if context_window_error:
                    return Response(
                        {
                            "error": context_window_error.get("error"),
                            "error_type": "context_window_exceeded",
                            "token_count": context_window_error.get("token_count"),
                            "context_limit": context_window_error.get("context_limit"),
                            "model": context_window_error.get("model"),
                            "_lookup_metadata": metadata,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    # Other failure - return first error
                    first_error = failed_enrichments[0]
                    return Response(
                        {
                            "error": first_error.get("error", "Look-Up execution failed"),
                            "_lookup_metadata": metadata,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Serialize response
            response_serializer = LookupExecutionResponseSerializer(data=result)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)

        except ExtractionNotCompleteError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(f"Error executing Look-Up project {project.id}")
            return Response(
                {"error": "Internal error during execution"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def upload_reference_data(self, request, pk=None):
        """Upload reference data for a Look-Up project.

        POST /api/v1/lookup-projects/{id}/upload_reference_data/
        """
        project = self.get_object()

        upload_serializer = ReferenceDataUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        file = upload_serializer.validated_data["file"]
        extract_text = upload_serializer.validated_data["extract_text"]

        try:
            from utils.file_storage.helpers.prompt_studio_file_helper import (
                PromptStudioFileHelper,
            )
            from utils.user_context import UserContext

            # Determine file type from extension
            file_ext = file.name.split(".")[-1].lower()
            file_type = (
                file_ext
                if file_ext in ["pdf", "xlsx", "csv", "docx", "txt", "json"]
                else "txt"
            )

            org_id = UserContext.get_organization_identifier()
            # Use a fixed user_id for lookup uploads to match PS path structure
            # Path: {base_path}/{org_id}/{user_id}/{tool_id}/{filename}
            user_id = "lookup"
            tool_id = str(project.id)

            logger.info(
                f"Upload via PromptStudioFileHelper: org_id={org_id}, "
                f"user_id={user_id}, tool_id={tool_id}, file={file.name}"
            )

            # Use PromptStudioFileHelper - exact same code path as working PS upload
            PromptStudioFileHelper.upload_for_ide(
                org_id=org_id,
                user_id=user_id,
                tool_id=tool_id,
                file_name=file.name,
                file_data=file,
            )

            # Build file_path for database record (matching PS helper's path structure)
            from pathlib import Path

            from utils.file_storage.constants import FileStorageConstants

            from unstract.core.utilities import UnstractUtils

            base_path = UnstractUtils.get_env(
                env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
            )
            file_path = str(Path(base_path) / org_id / user_id / tool_id / file.name)

            logger.info(f"Uploaded file to storage: {file_path}")

            # Create a data source record
            data_source = LookupDataSource.objects.create(
                project=project,
                file_name=file.name,
                file_path=file_path,
                file_size=file.size,
                file_type=file_type,
                extraction_status="pending" if extract_text else "completed",
                uploaded_by=request.user,
            )

            serializer = LookupDataSourceSerializer(data_source)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception(
                f"Error uploading reference data for project {project.id}: {e}"
            )
            return Response(
                {"error": f"Failed to upload file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def data_sources(self, request, pk=None):
        """List all data sources for a Look-Up project.

        GET /api/v1/lookup-projects/{id}/data_sources/
        """
        project = self.get_object()
        data_sources = project.data_sources.all().order_by("-version_number")

        # Filter by is_latest if requested
        is_latest = request.query_params.get("is_latest")
        if is_latest is not None:
            data_sources = data_sources.filter(is_latest=is_latest.lower() == "true")

        serializer = LookupDataSourceSerializer(data_sources, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cleanup_stale_indexes(self, request, pk=None):
        """Manually trigger cleanup of stale vector DB indexes for a project.

        POST /api/v1/lookup-projects/{id}/cleanup_stale_indexes/

        Cleans up vector DB nodes that are marked as stale or no longer needed.
        This is useful for reclaiming storage and ensuring data consistency.

        Returns:
            Summary of cleanup operations performed.
        """
        project = self.get_object()

        try:
            from lookup.models import LookupIndexManager
            from lookup.services.vector_db_cleanup_service import (
                VectorDBCleanupService,
            )

            cleanup_service = VectorDBCleanupService()
            total_deleted = 0
            total_failed = 0
            errors = []

            # Get all index managers for this project that need cleanup
            index_managers = LookupIndexManager.objects.filter(
                data_source__project=project
            ).select_related("profile_manager", "data_source")

            for index_manager in index_managers:
                if not index_manager.profile_manager:
                    continue

                # Clean up stale indexes (keeping only the current one)
                result = cleanup_service.cleanup_stale_indexes(
                    index_manager=index_manager, keep_current=True
                )
                total_deleted += result.get("deleted", 0)
                total_failed += result.get("failed", 0)
                if result.get("errors"):
                    errors.extend(result["errors"])

                # Reset reindex_required flag if cleanup was successful
                if result.get("success"):
                    index_manager.reindex_required = False
                    index_manager.save(update_fields=["reindex_required"])

            return Response(
                {
                    "message": "Cleanup completed",
                    "project_id": str(project.id),
                    "indexes_deleted": total_deleted,
                    "indexes_failed": total_failed,
                    "errors": errors[:10] if errors else [],  # Limit errors shown
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(f"Error during cleanup for project {project.id}")
            return Response(
                {"error": f"Cleanup failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def index_all(self, request, pk=None):
        """Index all reference data using the project's default profile.

        POST /api/v1/lookup-projects/{id}/index_all/

        Triggers indexing of all completed data sources using the
        configured default profile's adapters and settings.

        This calls external extraction and indexing services via PromptTool SDK.
        """
        project = self.get_object()

        try:
            from utils.user_context import UserContext

            from .exceptions import DefaultProfileError
            from .services import IndexingService

            # Get organization and user context
            org_id = UserContext.get_organization_identifier()
            user_id = str(request.user.user_id) if request.user else None

            logger.info(
                f"Starting indexing for project {project.id} "
                f"(org: {org_id}, user: {user_id})"
            )

            # Index all using default profile
            results = IndexingService.index_with_default_profile(
                project_id=str(project.id), org_id=org_id, user_id=user_id
            )

            logger.info(
                f"Indexing completed for project {project.id}: "
                f"{results['success']} successful, {results['failed']} failed"
            )

            return Response(
                {"message": "Indexing completed", "results": results},
                status=status.HTTP_200_OK,
            )

        except DefaultProfileError as e:
            logger.error(f"Default profile error for project {project.id}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error indexing reference data for project {project.id}")
            return Response(
                {"error": f"Failed to index reference data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LookupPromptTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Look-Up prompt templates.

    Provides CRUD operations and template validation.
    """

    queryset = LookupPromptTemplate.objects.all()
    serializer_class = LookupPromptTemplateSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        """Filter templates by active status if requested."""
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def perform_create(self, serializer):
        """Set created_by from request and update project's template reference."""
        template = serializer.save(created_by=self.request.user)
        # Update the project's template field to point to this template
        if template.project:
            template.project.template = template
            template.project.save(update_fields=["template"])

    def perform_update(self, serializer):
        """Update template and ensure project reference is maintained."""
        template = serializer.save()
        # Ensure the project's template field points to this template
        if template.project and template.project.template != template:
            template.project.template = template
            template.project.save(update_fields=["template"])

    @action(detail=False, methods=["post"])
    def validate(self, request):
        """Validate a template with optional sample data.

        POST /api/v1/lookup-templates/validate/
        """
        validator = TemplateValidationSerializer(data=request.data)
        validator.is_valid(raise_exception=True)

        template_text = validator.validated_data["template_text"]
        sample_data = validator.validated_data.get("sample_data", {})
        sample_reference = validator.validated_data.get("sample_reference", "")

        try:
            # Test variable resolution
            resolver = VariableResolver(sample_data, sample_reference)
            resolved = resolver.resolve(template_text)

            return Response(
                {
                    "valid": True,
                    "resolved_template": resolved[:1000],  # First 1000 chars
                    "variables_found": list(resolver.get_all_variables(template_text)),
                }
            )

        except Exception as e:
            return Response(
                {"valid": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )


class PromptStudioLookupLinkViewSet(viewsets.ModelViewSet):
    """ViewSet for managing links between Prompt Studio projects and Look-Ups."""

    queryset = PromptStudioLookupLink.objects.all()
    serializer_class = PromptStudioLookupLinkSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        """Filter links by PS project if requested."""
        queryset = super().get_queryset()

        ps_project_id = self.request.query_params.get("prompt_studio_project_id")
        if ps_project_id:
            queryset = queryset.filter(prompt_studio_project_id=ps_project_id)

        lookup_project_id = self.request.query_params.get("lookup_project_id")
        if lookup_project_id:
            queryset = queryset.filter(lookup_project_id=lookup_project_id)

        return queryset.select_related("lookup_project")

    @action(detail=False, methods=["post"])
    def bulk_link(self, request):
        """Create or remove multiple links at once.

        POST /api/v1/lookup-links/bulk_link/
        """
        serializer = BulkLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ps_project_id = serializer.validated_data["prompt_studio_project_id"]
        lookup_project_ids = serializer.validated_data["lookup_project_ids"]
        unlink = serializer.validated_data["unlink"]

        results = []

        with transaction.atomic():
            for lookup_id in lookup_project_ids:
                if unlink:
                    # Remove link
                    deleted_count, _ = PromptStudioLookupLink.objects.filter(
                        prompt_studio_project_id=ps_project_id,
                        lookup_project_id=lookup_id,
                    ).delete()
                    results.append(
                        {
                            "lookup_project_id": str(lookup_id),
                            "unlinked": deleted_count > 0,
                        }
                    )
                else:
                    # Create link
                    link, created = PromptStudioLookupLink.objects.get_or_create(
                        prompt_studio_project_id=ps_project_id,
                        lookup_project_id=lookup_id,
                    )
                    results.append(
                        {
                            "lookup_project_id": str(lookup_id),
                            "linked": created,
                            "link_id": str(link.id) if created else None,
                        }
                    )

        return Response({"results": results, "total_processed": len(results)})


class LookupExecutionAuditViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing execution audit records.

    Read-only access to execution history and statistics.
    """

    queryset = LookupExecutionAudit.objects.all()
    serializer_class = LookupExecutionAuditSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter audit records by various parameters."""
        queryset = super().get_queryset()

        # Filter by Look-Up project
        lookup_project_id = self.request.query_params.get("lookup_project_id")
        if lookup_project_id:
            queryset = queryset.filter(lookup_project_id=lookup_project_id)

        # Filter by PS project
        ps_project_id = self.request.query_params.get("prompt_studio_project_id")
        if ps_project_id:
            queryset = queryset.filter(prompt_studio_project_id=ps_project_id)

        # Filter by execution ID
        execution_id = self.request.query_params.get("execution_id")
        if execution_id:
            queryset = queryset.filter(execution_id=execution_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.select_related("lookup_project").order_by("-executed_at")

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """Get execution statistics for a project.

        GET /api/v1/execution-audits/statistics/?lookup_project_id={id}
        """
        lookup_project_id = request.query_params.get("lookup_project_id")
        if not lookup_project_id:
            return Response(
                {"error": "lookup_project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            audit_logger = AuditLogger()
            stats = audit_logger.get_project_stats(
                project_id=uuid.UUID(lookup_project_id), limit=1000
            )
            return Response(stats)

        except ValueError:
            return Response(
                {"error": "Invalid UUID format"}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["get"])
    def by_file_execution(self, request):
        """Get Look-up audits for a specific file execution.

        GET /api/v1/execution-audits/by_file_execution/?file_execution_id={id}

        This endpoint is used by the Nav Bar Logs page to show Look-up
        enrichment details for a specific file processed in ETL/Workflow/API.
        """
        file_execution_id = request.query_params.get("file_execution_id")
        if not file_execution_id:
            return Response(
                {"error": "file_execution_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            audits = self.get_queryset().filter(file_execution_id=file_execution_id)
            serializer = self.get_serializer(audits, many=True)
            return Response(serializer.data)
        except ValueError:
            return Response(
                {"error": "Invalid UUID format"}, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["get"])
    def by_workflow_execution(self, request):
        """Get Look-up audits for an entire workflow execution.

        GET /api/v1/execution-audits/by_workflow_execution/?workflow_execution_id={id}

        This endpoint returns all Look-up audits across all files
        processed in a workflow execution.
        """
        workflow_execution_id = request.query_params.get("workflow_execution_id")
        if not workflow_execution_id:
            return Response(
                {"error": "workflow_execution_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from workflow_manager.file_execution.models import WorkflowFileExecution

            # Get all file execution IDs for this workflow
            file_execution_ids = WorkflowFileExecution.objects.filter(
                workflow_execution_id=workflow_execution_id
            ).values_list("id", flat=True)

            audits = self.get_queryset().filter(file_execution_id__in=file_execution_ids)
            serializer = self.get_serializer(audits, many=True)
            return Response(serializer.data)
        except ValueError:
            return Response(
                {"error": "Invalid UUID format"}, status=status.HTTP_400_BAD_REQUEST
            )


class LookupDebugView(viewsets.ViewSet):
    """Debug endpoints for testing Look-Up execution with Prompt Studio."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def enrich_ps_output(self, request):
        """Enrich Prompt Studio extracted output with linked Look-Ups.

        Uses real LLM clients configured in each Look-Up project's profile.

        POST /api/v1/lookup-debug/enrich_ps_output/

        Request body:
            {
                "prompt_studio_project_id": "uuid",
                "extracted_data": {"vendor_name": "Amzn Web Services Inc", ...}
            }

        Response:
            {
                "original_data": {...},
                "enriched_data": {...},
                "lookup_enrichment": {...},
                "_lookup_metadata": {...}
            }
        """
        ps_project_id = request.data.get("prompt_studio_project_id")
        extracted_data = request.data.get("extracted_data", {})

        if not ps_project_id:
            return Response(
                {"error": "prompt_studio_project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not extracted_data:
            return Response(
                {"error": "extracted_data is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get linked Look-Ups
            links = (
                PromptStudioLookupLink.objects.filter(
                    prompt_studio_project_id=ps_project_id
                )
                .select_related("lookup_project")
                .order_by("execution_order")
            )

            if not links:
                return Response(
                    {
                        "original_data": extracted_data,
                        "enriched_data": extracted_data,
                        "lookup_enrichment": {},
                        "_lookup_metadata": {
                            "lookups_executed": 0,
                            "message": "No Look-Ups linked to this Prompt Studio project",
                        },
                    }
                )

            # Get Look-Up projects (already ordered by execution_order from query)
            lookup_projects = [link.lookup_project for link in links]

            # Initialize services with real clients
            from utils.user_context import UserContext

            from .integrations.file_storage_client import FileStorageClient
            from .integrations.unstract_llm_client import UnstractLLMClient

            # Get organization ID for RAG retrieval
            org_id = UserContext.get_organization_identifier()

            storage_client = FileStorageClient()
            cache = LLMResponseCache()
            ref_loader = ReferenceDataLoader(storage_client)
            merger = EnrichmentMerger()

            # Build project order mapping for sorting results later
            # This ensures enrichments are merged in execution_order priority
            project_order = {
                str(project.id): idx for idx, project in enumerate(lookup_projects)
            }

            # Execute each Look-Up with its own LLM profile
            # Collect results with project IDs for proper ordering
            enrichment_results = []
            all_metadata = {"lookups_executed": 0, "lookup_details": []}

            for project in lookup_projects:
                # Get profile for this project
                profile = LookupProfileManager.objects.filter(
                    lookup_project=project
                ).first()

                if not profile or not profile.llm:
                    all_metadata["lookup_details"].append(
                        {
                            "project_id": str(project.id),
                            "project_name": project.name,
                            "status": "skipped",
                            "reason": "No LLM profile configured",
                        }
                    )
                    continue

                try:
                    # Create LLM client for this project's profile
                    llm_client = UnstractLLMClient(profile.llm)

                    executor = LookUpExecutor(
                        variable_resolver=VariableResolver,
                        cache_manager=cache,
                        reference_loader=ref_loader,
                        llm_client=llm_client,
                        org_id=org_id,
                    )

                    orchestrator = LookUpOrchestrator(executor=executor, merger=merger)

                    # Execute Look-Up with extracted data as input
                    result = orchestrator.execute_lookups(
                        input_data=extracted_data, lookup_projects=[project]
                    )

                    # Collect results with project ID for ordering
                    if result.get("lookup_enrichment"):
                        enrichment_results.append(
                            {
                                "project_id": str(project.id),
                                "enrichment": result["lookup_enrichment"],
                            }
                        )

                    all_metadata["lookups_executed"] += 1
                    all_metadata["lookup_details"].append(
                        {
                            "project_id": str(project.id),
                            "project_name": project.name,
                            "status": "success",
                            "enrichment_keys": list(
                                result.get("lookup_enrichment", {}).keys()
                            ),
                        }
                    )

                except Exception as e:
                    logger.exception(f"Error executing Look-Up {project.id}")
                    all_metadata["lookup_details"].append(
                        {
                            "project_id": str(project.id),
                            "project_name": project.name,
                            "status": "error",
                            "error": str(e),
                        }
                    )

            # Sort enrichment results by execution order (first lookup has priority)
            enrichment_results.sort(
                key=lambda x: project_order.get(x.get("project_id"), 999)
            )

            # Merge enrichments in REVERSE order so first lookup wins
            # (later updates overwrite, so process highest priority last)
            all_enrichment = {}
            for result in reversed(enrichment_results):
                all_enrichment.update(result["enrichment"])

            # Merge enrichment into extracted data
            enriched_data = {**extracted_data, **all_enrichment}

            return Response(
                {
                    "original_data": extracted_data,
                    "enriched_data": enriched_data,
                    "lookup_enrichment": all_enrichment,
                    "_lookup_metadata": all_metadata,
                }
            )

        except Exception as e:
            logger.exception(f"Error enriching PS output for project {ps_project_id}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"])
    def test_with_ps_project(self, request):
        """Test Look-Up execution with a Prompt Studio project context.

        POST /api/v1/lookup-debug/test_with_ps_project/
        """
        ps_project_id = request.data.get("prompt_studio_project_id")
        input_data = request.data.get("input_data", {})

        if not ps_project_id:
            return Response(
                {"error": "prompt_studio_project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get linked Look-Ups
            links = PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=ps_project_id
            ).select_related("lookup_project")

            if not links:
                return Response(
                    {
                        "message": "No Look-Ups linked to this Prompt Studio project",
                        "lookup_enrichment": {},
                        "_lookup_metadata": {"lookups_executed": 0},
                    }
                )

            # Get Look-Up projects
            lookup_projects = [link.lookup_project for link in links]

            # Initialize services
            from utils.user_context import UserContext

            from .services.mock_clients import MockLLMClient, MockStorageClient

            # Get organization ID for RAG retrieval
            org_id = UserContext.get_organization_identifier()

            llm_client = MockLLMClient()
            storage_client = MockStorageClient()
            cache = LLMResponseCache()
            ref_loader = ReferenceDataLoader(storage_client)
            merger = EnrichmentMerger()

            executor = LookUpExecutor(
                variable_resolver=VariableResolver,
                cache_manager=cache,
                reference_loader=ref_loader,
                llm_client=llm_client,
                org_id=org_id,
            )

            orchestrator = LookUpOrchestrator(executor=executor, merger=merger)

            # Execute Look-Ups
            result = orchestrator.execute_lookups(
                input_data=input_data, lookup_projects=lookup_projects
            )

            return Response(result)

        except Exception as e:
            logger.exception(f"Error in debug execution for PS project {ps_project_id}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"])
    def check_indexing_status(self, request):
        """Check indexing status and optionally test vector DB retrieval.

        POST /api/v1/lookup-debug/check_indexing_status/

        Request body:
            {
                "project_id": "uuid",
                "test_query": "optional query to test retrieval"
            }

        Returns detailed status of data sources, index managers, and vector DB.
        """
        from lookup.models import LookupIndexManager

        project_id = request.data.get("project_id")
        test_query = request.data.get("test_query")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = LookupProject.objects.get(id=project_id)
        except LookupProject.DoesNotExist:
            return Response(
                {"error": f"Project not found: {project_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get profile
        try:
            profile = LookupProfileManager.get_default_profile(project)
        except Exception as e:
            return Response(
                {"error": f"No default profile: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = {
            "project": {
                "id": str(project.id),
                "name": project.name,
            },
            "profile": {
                "name": profile.profile_name,
                "chunk_size": profile.chunk_size,
                "chunk_overlap": profile.chunk_overlap,
                "similarity_top_k": profile.similarity_top_k,
                "vector_store_id": str(profile.vector_store.id),
                "embedding_model_id": str(profile.embedding_model.id),
                "rag_enabled": profile.chunk_size > 0,
            },
            "data_sources": [],
            "index_managers": [],
            "retrieval_test": None,
        }

        # Check data sources
        data_sources = LookupDataSource.objects.filter(project_id=project_id).order_by(
            "-created_at"
        )

        for ds in data_sources:
            result["data_sources"].append(
                {
                    "id": str(ds.id),
                    "file_name": ds.file_name,
                    "extraction_status": ds.extraction_status,
                    "is_latest": ds.is_latest,
                    "file_path": ds.file_path,
                }
            )

        # Check index managers
        index_managers = LookupIndexManager.objects.filter(
            data_source__project_id=project_id,
            profile_manager=profile,
        ).select_related("data_source")

        for im in index_managers:
            result["index_managers"].append(
                {
                    "data_source": im.data_source.file_name,
                    "raw_index_id": im.raw_index_id,
                    "has_index": im.raw_index_id is not None,
                    "extraction_status": im.extraction_status,
                    "index_ids_history": im.index_ids_history,
                }
            )

        # Test retrieval if query provided
        if test_query and profile.chunk_size > 0:
            try:
                from utils.user_context import UserContext

                from lookup.services.lookup_retrieval_service import (
                    LookupRetrievalService,
                )

                org_id = UserContext.get_organization_identifier()
                service = LookupRetrievalService(profile, org_id=org_id)
                context = service.retrieve_context(test_query, str(project.id))

                result["retrieval_test"] = {
                    "query": test_query,
                    "success": bool(context),
                    "context_length": len(context) if context else 0,
                    "context_preview": context[:500] if context else None,
                }
            except Exception as e:
                logger.exception("Retrieval test failed")
                result["retrieval_test"] = {
                    "query": test_query,
                    "success": False,
                    "error": str(e),
                }

        return Response(result)

    @action(detail=False, methods=["post"])
    def force_reindex(self, request):
        """Force re-indexing of all data sources for a project.

        POST /api/v1/lookup-debug/force_reindex/

        Request body:
            {
                "project_id": "uuid"
            }
        """
        from utils.user_context import UserContext

        from lookup.services.indexing_service import IndexingService

        project_id = request.data.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            org_id = UserContext.get_organization_identifier()
            user_id = str(request.user.id) if request.user else None

            result = IndexingService.index_with_default_profile(
                project_id=project_id,
                org_id=org_id,
                user_id=user_id,
            )

            return Response(
                {
                    "status": "success",
                    "total": result["total"],
                    "success": result["success"],
                    "failed": result["failed"],
                    "errors": result.get("errors", []),
                }
            )

        except Exception as e:
            logger.exception(f"Re-indexing failed for project {project_id}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LookupDataSourceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing LookupDataSource instances.

    Provides CRUD operations for Look-Up data sources (reference data files).
    Supports listing, retrieving, and deleting data sources.
    """

    queryset = LookupDataSource.objects.all()
    serializer_class = LookupDataSourceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    @action(detail=True, methods=["post"])
    def cleanup_indexes(self, request, pk=None):
        """Clean up vector DB indexes for a specific data source.

        POST /api/v1/data-sources/{id}/cleanup_indexes/

        Cleans up all vector DB nodes associated with this data source.
        Use this before re-uploading a data source or when indexes are corrupted.

        Returns:
            Summary of cleanup operations performed.
        """
        data_source = self.get_object()

        try:
            from lookup.models import LookupIndexManager
            from lookup.services.vector_db_cleanup_service import (
                VectorDBCleanupService,
            )

            cleanup_service = VectorDBCleanupService()
            total_deleted = 0
            total_failed = 0
            errors = []

            # Get all index managers for this data source
            index_managers = LookupIndexManager.objects.filter(
                data_source=data_source
            ).select_related("profile_manager")

            for index_manager in index_managers:
                if not index_manager.profile_manager:
                    continue

                if index_manager.index_ids_history:
                    result = cleanup_service.cleanup_index_ids(
                        index_ids=index_manager.index_ids_history,
                        vector_db_instance_id=str(
                            index_manager.profile_manager.vector_store_id
                        ),
                    )
                    total_deleted += result.get("deleted", 0)
                    total_failed += result.get("failed", 0)
                    if result.get("errors"):
                        errors.extend(result["errors"])

                    # Clear history if cleanup was successful
                    if result.get("success"):
                        index_manager.index_ids_history = []
                        index_manager.raw_index_id = None
                        index_manager.reindex_required = True
                        index_manager.save(
                            update_fields=[
                                "index_ids_history",
                                "raw_index_id",
                                "reindex_required",
                            ]
                        )

            return Response(
                {
                    "message": "Cleanup completed",
                    "data_source_id": str(data_source.id),
                    "file_name": data_source.file_name,
                    "indexes_deleted": total_deleted,
                    "indexes_failed": total_failed,
                    "errors": errors[:10] if errors else [],
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(f"Error during cleanup for data source {data_source.id}")
            return Response(
                {"error": f"Cleanup failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get_queryset(self):
        """Filter data sources by project if specified."""
        queryset = super().get_queryset()

        # Filter by project if provided
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        # Filter by is_latest if requested
        is_latest = self.request.query_params.get("is_latest")
        if is_latest is not None:
            queryset = queryset.filter(is_latest=is_latest.lower() == "true")

        return queryset.select_related("project", "uploaded_by").order_by(
            "-version_number"
        )

    def destroy(self, request, *args, **kwargs):
        """Delete a data source and its associated files from storage.

        DELETE /api/v1/unstract/{org_id}/data-sources/{id}/
        """
        instance = self.get_object()

        try:
            from utils.file_storage.constants import FileStorageKeys

            from unstract.sdk1.file_storage.constants import StorageType
            from unstract.sdk1.file_storage.env_helper import EnvHelper

            # Get file storage instance
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )

            # Delete the file from storage if it exists
            if instance.file_path:
                try:
                    if fs_instance.exists(instance.file_path):
                        fs_instance.rm(instance.file_path)
                        logger.info(f"Deleted file from storage: {instance.file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file from storage: {e}")

            # Delete extracted content if it exists
            if instance.extracted_content_path:
                try:
                    if fs_instance.exists(instance.extracted_content_path):
                        fs_instance.rm(instance.extracted_content_path)
                        logger.info(
                            f"Deleted extracted content: {instance.extracted_content_path}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to delete extracted content: {e}")

            # Delete associated index manager if exists
            try:
                from .models import LookupIndexManager

                LookupIndexManager.objects.filter(data_source=instance).delete()
                logger.info(f"Deleted index manager for data source: {instance.id}")
            except Exception as e:
                logger.warning(f"Failed to delete index manager: {e}")

            # Delete the database record
            instance.delete()

            logger.info(f"Successfully deleted data source: {instance.id}")
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.exception(f"Error deleting data source {instance.id}")
            return Response(
                {"error": f"Failed to delete data source: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LookupProfileManagerViewSet(viewsets.ModelViewSet):
    """ViewSet for managing LookupProfileManager instances.

    Provides CRUD operations for Look-Up project profiles.
    Each profile defines the set of adapters to use for a Look-Up project.

    Follows the same pattern as Prompt Studio's ProfileManagerView.
    """

    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    serializer_class = LookupProfileManagerSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        """Filter queryset by created_by if specified in query params.
        Otherwise return all profiles the user has access to.
        """
        filter_args = FilterHelper.build_filter_args(
            self.request,
            LookupProfileManagerKeys.CREATED_BY,
        )
        if filter_args:
            queryset = LookupProfileManager.objects.filter(**filter_args)
        else:
            queryset = LookupProfileManager.objects.all()

        # Filter by lookup_project if provided in query params
        lookup_project_id = self.request.query_params.get("lookup_project")
        if lookup_project_id:
            queryset = queryset.filter(lookup_project_id=lookup_project_id)

        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        """Create a new profile.

        Handles IntegrityError for duplicate profile names within the same project.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(LookupProfileManagerErrors.PROFILE_NAME_EXISTS)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="default")
    def get_default(self, request):
        """Get the default profile for a lookup project.

        Query params:
            - lookup_project: UUID of the lookup project (required)

        Returns:
            Profile data or 404 if no default profile exists
        """
        lookup_project_id = request.query_params.get("lookup_project")

        if not lookup_project_id:
            return Response(
                {"error": "lookup_project query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = LookupProject.objects.get(id=lookup_project_id)
            profile = LookupProfileManager.get_default_profile(project)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except LookupProject.DoesNotExist:
            return Response(
                {"error": "Lookup project not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        """Set a profile as the default for its project.

        Unsets any existing default profile for the same project.
        """
        profile = self.get_object()

        with transaction.atomic():
            # Unset existing default for this project
            LookupProfileManager.objects.filter(
                lookup_project=profile.lookup_project, is_default=True
            ).update(is_default=False)

            # Set this profile as default
            profile.is_default = True
            profile.save()

        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """Update a profile and mark indexes as stale if RAG settings changed.

        When chunk_size, chunk_overlap, embedding_model, or vector_store
        are changed, existing indexes become stale and need re-indexing.
        """
        profile = self.get_object()

        # Track original values for RAG-relevant fields
        original_values = {
            "chunk_size": profile.chunk_size,
            "chunk_overlap": profile.chunk_overlap,
            "embedding_model": str(profile.embedding_model_id)
            if profile.embedding_model
            else None,
            "vector_store": str(profile.vector_store_id)
            if profile.vector_store
            else None,
        }

        # Perform the update
        response = super().partial_update(request, *args, **kwargs)

        # Check if any RAG-relevant fields changed
        if response.status_code == status.HTTP_200_OK:
            profile.refresh_from_db()

            new_values = {
                "chunk_size": profile.chunk_size,
                "chunk_overlap": profile.chunk_overlap,
                "embedding_model": str(profile.embedding_model_id)
                if profile.embedding_model
                else None,
                "vector_store": str(profile.vector_store_id)
                if profile.vector_store
                else None,
            }

            # Determine if re-indexing is needed
            rag_settings_changed = original_values != new_values
            was_rag_mode = (
                original_values["chunk_size"] and original_values["chunk_size"] > 0
            )
            is_rag_mode = new_values["chunk_size"] and new_values["chunk_size"] > 0

            if rag_settings_changed and (was_rag_mode or is_rag_mode):
                # Mark all indexes for this profile as requiring re-index
                from lookup.models import LookupIndexManager

                updated_count = LookupIndexManager.objects.filter(
                    profile_manager=profile
                ).update(reindex_required=True)

                if updated_count > 0:
                    logger.info(
                        f"Marked {updated_count} index(es) as requiring re-index "
                        f"for profile {profile.profile_name}"
                    )

                # If switching from RAG to full context mode, clean up old indexes
                if was_rag_mode and not is_rag_mode:
                    from lookup.services.vector_db_cleanup_service import (
                        VectorDBCleanupService,
                    )

                    cleanup_service = VectorDBCleanupService()
                    cleanup_result = cleanup_service.cleanup_for_profile(
                        str(profile.profile_id)
                    )
                    logger.info(
                        f"Cleaned up {cleanup_result['deleted']} index(es) "
                        f"after switching profile {profile.profile_name} to full context mode"
                    )

        return response
