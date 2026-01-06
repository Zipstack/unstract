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
            from .integrations.file_storage_client import FileStorageClient
            from .integrations.unstract_llm_client import UnstractLLMClient

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
            from django.conf import settings
            from utils.file_storage.constants import FileStorageKeys

            from unstract.sdk1.file_storage.constants import StorageType
            from unstract.sdk1.file_storage.env_helper import EnvHelper

            # Get file storage instance
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )

            # Determine file type from extension
            file_ext = file.name.split(".")[-1].lower()
            file_type = (
                file_ext
                if file_ext in ["pdf", "xlsx", "csv", "docx", "txt", "json"]
                else "txt"
            )

            # Upload file to storage following Prompt Studio's path structure
            # Pattern: {base_path}/{org_id}/{project_id}/{filename}
            # Keep Lookup file storage independent of PS project linkage
            from utils.user_context import UserContext

            org_id = UserContext.get_organization_identifier()
            base_path = settings.PROMPT_STUDIO_FILE_PATH

            # Store files under Lookup project ID, not PS tool ID
            # This ensures files remain accessible regardless of PS linkage changes
            file_path = f"{base_path}/{org_id}/{project.id}/{file.name}"

            # Create parent directories if they don't exist
            fs_instance.mkdir(f"{base_path}/{org_id}/{project.id}", create_parents=True)
            fs_instance.mkdir(
                f"{base_path}/{org_id}/{project.id}/extract", create_parents=True
            )

            # Upload the file
            fs_instance.write(path=file_path, mode="wb", data=file.read())

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

        except Exception:
            logger.exception(f"Error uploading reference data for project {project.id}")
            return Response(
                {"error": "Failed to upload reference data"},
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
            from .integrations.file_storage_client import FileStorageClient
            from .integrations.unstract_llm_client import UnstractLLMClient

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
            from .services.mock_clients import MockLLMClient, MockStorageClient

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


class LookupDataSourceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing LookupDataSource instances.

    Provides CRUD operations for Look-Up data sources (reference data files).
    Supports listing, retrieving, and deleting data sources.
    """

    queryset = LookupDataSource.objects.all()
    serializer_class = LookupDataSourceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

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
