"""ViewSets for Agentic Studio V2 REST API."""

import logging
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from permissions.permission import IsOrganizationMember, IsOwner
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.user_context import UserContext

from .models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticExtractionNote,
    AgenticExtractedData,
    AgenticLog,
    AgenticProject,
    AgenticPromptVersion,
    AgenticSchema,
    AgenticSetting,
    AgenticSummary,
    AgenticVerifiedData,
)
from .serializers import (
    AgenticComparisonResultSerializer,
    AgenticDocumentSerializer,
    AgenticExtractionNoteSerializer,
    AgenticExtractedDataSerializer,
    AgenticLogSerializer,
    AgenticProjectSerializer,
    AgenticPromptVersionSerializer,
    AgenticSchemaSerializer,
    AgenticSettingSerializer,
    AgenticSummarySerializer,
    AgenticVerifiedDataSerializer,
)

logger = logging.getLogger(__name__)


class AgenticProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Agentic Projects.

    Provides CRUD operations plus:
    - pipeline_status: Get current pipeline processing status
    - start_pipeline: Trigger full pipeline execution
    - accuracy_overview: Get project-level accuracy metrics
    """

    queryset = AgenticProject.objects.all()
    serializer_class = AgenticProjectSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Filter projects by organization."""
        organization = UserContext.get_organization()
        if organization:
            return AgenticProject.objects.filter(organization=organization)
        return AgenticProject.objects.none()

    @action(detail=True, methods=["get"])
    def pipeline_status(self, request: Request, pk=None) -> Response:
        """Get current pipeline processing status for a project.

        Returns status for each stage: raw_text, summary, schema, prompt, extraction
        """
        project = self.get_object()

        # TODO: Integrate with StateManager when services are implemented
        status_data = {
            "project_id": str(project.id),
            "project_name": project.name,
            "stages": {
                "raw_text": {
                    "status": "pending",
                    "progress": 0,
                    "message": "Not started",
                },
                "summary": {
                    "status": "pending",
                    "progress": 0,
                    "message": "Not started",
                },
                "schema": {
                    "status": "pending",
                    "progress": 0,
                    "message": "Not started",
                },
                "prompt": {
                    "status": "pending",
                    "progress": 0,
                    "message": "Not started",
                },
                "extraction": {
                    "status": "pending",
                    "progress": 0,
                    "message": "Not started",
                },
            },
        }

        return Response(status_data)

    @action(detail=True, methods=["post"])
    def start_pipeline(self, request: Request, pk=None) -> Response:
        """Trigger full pipeline execution.

        This will kick off async Celery tasks for:
        1. Document text extraction (LLMWhisperer)
        2. Summarization (SummarizerAgent)
        3. Schema generation (Uniformer + Finalizer)
        4. Prompt generation (PromptArchitect)
        """
        project = self.get_object()

        # TODO: Trigger pipeline via Celery task
        # from .tasks import run_pipeline_task
        # job = run_pipeline_task.delay(str(project.id))

        return Response(
            {
                "message": "Pipeline started",
                "project_id": str(project.id),
                # "job_id": job.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def accuracy_overview(self, request: Request, pk=None) -> Response:
        """Get project-level accuracy metrics.

        Returns:
        - Overall accuracy across all prompt versions
        - Per-field accuracy breakdown
        - Error type distribution
        """
        project = self.get_object()

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response(
                {"message": "No active prompt version found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Calculate accuracy from comparison results
        comparisons = AgenticComparisonResult.objects.filter(
            project=project, prompt_version=active_prompt
        )

        total_fields = comparisons.count()
        matched_fields = comparisons.filter(match=True).count()
        overall_accuracy = (
            (matched_fields / total_fields * 100) if total_fields > 0 else 0
        )

        # Per-field accuracy
        field_accuracy = {}
        for field_path in comparisons.values_list("field_path", flat=True).distinct():
            field_comparisons = comparisons.filter(field_path=field_path)
            field_total = field_comparisons.count()
            field_matched = field_comparisons.filter(match=True).count()
            field_accuracy[field_path] = {
                "total": field_total,
                "matched": field_matched,
                "accuracy": (field_matched / field_total * 100) if field_total > 0 else 0,
            }

        # Error type distribution
        error_distribution = {}
        for error_type in AgenticComparisonResult.ErrorType.values:
            count = comparisons.filter(error_type=error_type).count()
            error_distribution[error_type] = count

        return Response(
            {
                "project_id": str(project.id),
                "prompt_version": active_prompt.version,
                "overall_accuracy": round(overall_accuracy, 2),
                "total_fields": total_fields,
                "matched_fields": matched_fields,
                "field_accuracy": field_accuracy,
                "error_distribution": error_distribution,
            }
        )

    @action(detail=True, methods=["get"], url_path="prompts/latest")
    def prompts_latest(self, request: Request, pk=None) -> Response:
        """Get the latest/active prompt version for a project."""
        project = self.get_object()
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response(
                {"prompts": [], "message": "No active prompt version found"},
                status=status.HTTP_200_OK,
            )

        return Response({
            "prompt_text": active_prompt.prompt_text,
            "version": active_prompt.version,
            "created_at": active_prompt.created_at.isoformat() if active_prompt.created_at else None,
        })

    @action(detail=True, methods=["get"], url_path="schema")
    def schema(self, request: Request, pk=None) -> Response:
        """Get the schema for a project."""
        import json

        project = self.get_object()
        schema = AgenticSchema.objects.filter(project=project, is_active=True).first()

        if not schema:
            return Response(
                {"schema": {}, "message": "No active schema found"},
                status=status.HTTP_200_OK,
            )

        # Parse json_schema if it's a string
        try:
            schema_data = json.loads(schema.json_schema) if isinstance(schema.json_schema, str) else schema.json_schema
        except (json.JSONDecodeError, TypeError):
            schema_data = {}

        return Response({
            "schema": schema_data,
            "version": schema.version,
            "created_at": schema.created_at.isoformat() if schema.created_at else None,
        })

    @action(detail=True, methods=["post"], url_path="schema/generate")
    def generate_schema(self, request: Request, pk=None) -> Response:
        """Generate schema from document summaries (synchronous).

        This is the "regular" mode - requires summaries to exist.

        Returns:
        - 200 OK with generated schema
        - 400 Bad Request if prerequisites not met
        - 500 Internal Server Error if generation fails
        """
        import requests
        from django.conf import settings

        project = self.get_object()
        organization_id = str(project.organization.organization_id)

        # Validate prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get Agent LLM adapter
        adapter_id = str(project.agent_llm_id)

        # Get all summaries for this project
        summaries = AgenticSummary.objects.filter(project=project)

        if not summaries.exists():
            return Response(
                {"error": "No summaries found for this project. Please process documents first or use lazy mode."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Format summaries for prompt-service
            import json
            summaries_data = []
            for summary in summaries:
                # Parse fields from summary_text (JSON-encoded fields array)
                try:
                    fields = json.loads(summary.summary_text)
                    if not isinstance(fields, list):
                        fields = []
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning(f"Failed to parse fields from summary {summary.id}, using empty array")
                    fields = []

                summaries_data.append({
                    "document_id": str(summary.document.id),
                    "summary_text": summary.summary_text,
                    "fields": fields,
                })

            logger.info(f"Starting schema generation for project {project.id} with {len(summaries_data)} summaries")

            # Get platform key for authentication
            from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
            platform_key = PlatformAuthenticationService.get_active_platform_key()
            headers = {
                "X-Platform-Key": str(platform_key.key) if platform_key else "",
            }

            # Call prompt-service to uniformize schemas
            prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
            prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
            prompt_service_url = f"{prompt_host}:{prompt_port}"

            # Step 1: Uniformize field candidates from all summaries
            uniformize_payload = {
                "project_id": str(project.id),
                "summaries": summaries_data,
                "organization_id": organization_id,
                "adapter_instance_id": adapter_id,
            }

            logger.info(f"Calling uniformize endpoint for project {project.id}")
            try:
                uniformize_response = requests.post(
                    f"{prompt_service_url}/agentic/uniformize",
                    json=uniformize_payload,
                    timeout=600,
                    headers=headers,
                )
            except requests.exceptions.Timeout:
                return Response(
                    {"error": "Schema uniformization timed out (10 minutes). The LLM may be slow or unavailable. Please try again."},
                    status=status.HTTP_504_GATEWAY_TIMEOUT,
                )
            except requests.exceptions.ConnectionError:
                return Response(
                    {"error": "Could not connect to prompt service for uniformization. Please check service status."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during uniformization: {e}")
                return Response(
                    {"error": f"Network error during uniformization: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if uniformize_response.status_code != 200:
                error_msg = f"Schema uniformization failed: {uniformize_response.text}"
                logger.error(error_msg)
                return Response(
                    {"error": error_msg},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            uniform_schema = uniformize_response.json().get("uniform_schema", {})

            # Step 2: Finalize schema to JSON Schema format
            finalize_payload = {
                "project_id": str(project.id),
                "uniform_schema": uniform_schema,
                "organization_id": organization_id,
                "adapter_instance_id": adapter_id,
            }

            logger.info(f"Calling finalize endpoint for project {project.id}")
            try:
                finalize_response = requests.post(
                    f"{prompt_service_url}/agentic/finalize",
                    json=finalize_payload,
                    timeout=600,
                    headers=headers,
                )
            except requests.exceptions.Timeout:
                return Response(
                    {"error": "Schema finalization timed out (10 minutes). The LLM may be slow or unavailable. Please try again."},
                    status=status.HTTP_504_GATEWAY_TIMEOUT,
                )
            except requests.exceptions.ConnectionError:
                return Response(
                    {"error": "Could not connect to prompt service for finalization. Please check service status."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during finalization: {e}")
                return Response(
                    {"error": f"Network error during finalization: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if finalize_response.status_code != 200:
                error_msg = f"Schema finalization failed: {finalize_response.text}"
                logger.error(error_msg)
                return Response(
                    {"error": error_msg},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            json_schema = finalize_response.json().get("json_schema", {})

            # Save the generated schema (update existing or create new)
            schema, created = AgenticSchema.objects.update_or_create(
                project=project,
                defaults={
                    "json_schema": json.dumps(json_schema) if isinstance(json_schema, dict) else json_schema,
                    "organization": project.organization,
                },
            )

            action = "created" if created else "updated"
            logger.info(f"Schema {action} for project {project.id}, schema_id: {schema.id}")

            logger.info(f"Schema generated successfully for project {project.id}, schema_id: {schema.id}")

            return Response(
                {
                    "message": "Schema generated successfully",
                    "schema_id": str(schema.id),
                    "project_id": str(project.id),
                    "schema": json_schema,
                    "summaries_count": len(summaries_data),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Schema generation failed for project {project.id}: {e}", exc_info=True)
            return Response(
                {"error": f"Schema generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="schema/generation-status")
    def schema_generation_status(self, request: Request, pk=None) -> Response:
        """Get status of regular schema generation."""
        from prompt_studio.agentic_studio_v2.services.state_manager import ProcessingStateManager

        project = self.get_object()
        state_mgr = ProcessingStateManager()
        status_data = state_mgr.get_stage_status(project_id=project.id, stage="schema")

        return Response(status_data or {"status": "not_started"})

    @action(detail=True, methods=["get"], url_path="schema/lazy-generation-status")
    def schema_lazy_generation_status(self, request: Request, pk=None) -> Response:
        """Get status of lazy schema generation (checks all stages)."""
        from prompt_studio.agentic_studio_v2.services.state_manager import ProcessingStateManager

        project = self.get_object()
        state_mgr = ProcessingStateManager()

        # Get status for all stages
        raw_text_status = state_mgr.get_stage_status(project_id=project.id, stage="raw_text")
        summary_status = state_mgr.get_stage_status(project_id=project.id, stage="summary")
        schema_status = state_mgr.get_stage_status(project_id=project.id, stage="schema")

        # Determine overall status
        if schema_status and schema_status.get("status") == "completed":
            overall_status = "completed"
            progress = 100
        elif schema_status and schema_status.get("status") in ["in_progress", "pending"]:
            overall_status = "in_progress"
            progress = schema_status.get("progress", 70)
        elif summary_status and summary_status.get("status") in ["in_progress", "pending"]:
            overall_status = "in_progress"
            progress = summary_status.get("progress", 50)
        elif raw_text_status and raw_text_status.get("status") in ["in_progress", "pending"]:
            overall_status = "in_progress"
            progress = raw_text_status.get("progress", 15)
        else:
            overall_status = "not_started"
            progress = 0

        return Response({
            "status": overall_status,
            "progress": progress,
            "raw_text": raw_text_status,
            "summary": summary_status,
            "schema": schema_status,
        })

    @action(detail=True, methods=["post"], url_path="process-pipeline")
    def process_pipeline(self, request: Request, pk=None) -> Response:
        """Trigger full lazy pipeline with auto-dependency handling (async via Celery).

        Similar to AutoPrompt's generate_schema_lazy_job.

        Phases:
        1. Raw text extraction (0-30%) - for documents missing raw_text
        2. Summarization (30-70%) - for documents missing summaries
        3. Schema generation (70-100%) - Uniformer + Finalizer

        Returns:
        - 202 Accepted with task_id for tracking
        - Use GET /processing/state endpoint to check progress
        """
        from prompt_studio.agentic_studio_v2.tasks import run_pipeline_task
        from prompt_studio.agentic_studio_v2.services.state_manager import ProcessingStateManager

        project = self.get_object()

        # Validate prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if project has documents
        documents_count = project.documents.count()
        if documents_count == 0:
            return Response(
                {"error": "No documents found in project. Please upload documents first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Analyze what needs to be done
            docs_needing_raw_text = project.documents.filter(raw_text__isnull=True).count()

            from .models import AgenticSummary
            docs_with_text = project.documents.exclude(raw_text__isnull=True)
            docs_needing_summaries = 0
            for doc in docs_with_text:
                if not AgenticSummary.objects.filter(document=doc).exists():
                    docs_needing_summaries += 1

            # Reset pipeline state
            state_mgr = ProcessingStateManager()
            state_mgr.reset_pipeline(project.id)

            # Enqueue pipeline task
            task = run_pipeline_task.delay(str(project.id))

            logger.info(f"Enqueued lazy pipeline for project {project.id}, task_id: {task.id}")

            estimated_phases = []
            if docs_needing_raw_text > 0:
                estimated_phases.append("raw_text")
            if docs_needing_summaries > 0:
                estimated_phases.append("summary")
            estimated_phases.append("schema")

            return Response(
                {
                    "message": "Pipeline started",
                    "task_id": task.id,
                    "project_id": str(project.id),
                    "total_documents": documents_count,
                    "docs_needing_raw_text": docs_needing_raw_text,
                    "docs_needing_summaries": docs_needing_summaries,
                    "estimated_phases": estimated_phases,
                    "status": "processing",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            logger.error(f"Failed to enqueue pipeline task: {e}")
            return Response(
                {"error": f"Failed to start pipeline: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="schema/generate-lazy")
    def generate_schema_lazy(self, request: Request, pk=None) -> Response:
        """Generate schema with lazy auto-dependency handling (synchronous).

        Phases:
        1. Raw text extraction (0-30%) - for documents missing raw_text
        2. Summarization (30-70%) - for documents missing summaries
        3. Schema generation (70-100%) - Uniformer + Finalizer

        Returns:
        - 200 OK with schema data upon success
        - 400 Bad Request if prerequisites not met
        - 500 Internal Server Error if generation fails
        """
        from .services import PipelineService
        from .serializers import AgenticSchemaSerializer

        project = self.get_object()

        # Validate prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if project has documents
        documents_count = project.documents.count()
        if documents_count == 0:
            return Response(
                {"error": "No documents found in project. Please upload documents first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Analyze what needs to be done
            docs_needing_raw_text = project.documents.filter(raw_text__isnull=True).count()

            docs_with_text = project.documents.exclude(raw_text__isnull=True)
            docs_needing_summaries = 0
            for doc in docs_with_text:
                if not AgenticSummary.objects.filter(document=doc).exists():
                    docs_needing_summaries += 1

            # Run pipeline synchronously
            logger.info(f"Starting synchronous lazy schema generation for project {project.id}")
            pipeline = PipelineService(str(project.id))
            result = pipeline.generate_schema_lazy()

            # Get the generated schema
            schema = AgenticSchema.objects.filter(project=project, is_active=True).first()
            if not schema:
                return Response(
                    {"error": "Schema generation completed but no schema was saved"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            logger.info(f"Schema generation completed successfully for project {project.id}")

            # Serialize and return the schema
            serializer = AgenticSchemaSerializer(schema)

            return Response(
                {
                    "message": "Schema generated successfully",
                    "schema": serializer.data,
                    "project_id": str(project.id),
                    "total_documents": documents_count,
                    "docs_processed_raw_text": docs_needing_raw_text,
                    "docs_processed_summaries": docs_needing_summaries,
                    "status": "completed",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Failed to generate schema: {e}", exc_info=True)
            return Response(
                {"error": f"Failed to generate schema: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="generate-prompt")
    def generate_prompt(self, request: Request, pk=None) -> Response:
        """Generate extraction prompt using 3-agent pipeline (synchronous).

        Uses PatternMiner → PromptArchitect → CriticDryRunner pipeline.

        Returns:
        - 200 OK with prompt data upon success
        - 400 Bad Request if prerequisites not met
        - 500 Internal Server Error if generation fails
        """
        from .services import PipelineService
        from .serializers import AgenticPromptVersionSerializer

        project = self.get_object()

        # Validate prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if schema exists
        schema = AgenticSchema.objects.filter(project=project, is_active=True).first()
        if not schema:
            return Response(
                {"error": "No active schema found. Please generate schema first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if summaries exist
        summaries_count = AgenticSummary.objects.filter(project=project).count()
        if summaries_count == 0:
            return Response(
                {"error": "No summaries found for this project. Please generate schema first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Run pipeline synchronously
            logger.info(f"Starting synchronous prompt generation for project {project.id}")
            pipeline = PipelineService(str(project.id))
            prompt_version = pipeline.generate_prompt()

            logger.info(f"Prompt generation completed for project {project.id}, version {prompt_version.version}")

            # Serialize and return the generated prompt
            serializer = AgenticPromptVersionSerializer(prompt_version)
            return Response(
                {
                    "message": "Prompt generated successfully",
                    "prompt": serializer.data,
                    "project_id": str(project.id),
                    "summaries_count": summaries_count,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Failed to generate prompt: {e}", exc_info=True)
            return Response(
                {"error": f"Failed to generate prompt: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="batch-extract")
    def batch_extract(self, request: Request, pk=None) -> Response:
        """Run batch extraction + auto-comparison (threaded, non-blocking).

        Extracts all documents with verified data and compares with verified data.

        Returns:
        - 202 Accepted with thread_id for tracking
        - Connect to WebSocket for real-time progress updates
        """
        from .services import PipelineService, ThreadingService

        project = self.get_object()

        # Validate prerequisites
        if not project.extractor_llm_id:
            return Response(
                {"error": "No Extractor LLM configured for this project. Please configure in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get active prompt
        active_prompt = project.prompt_versions.filter(is_active=True).first()
        if not active_prompt:
            return Response(
                {"error": "No active prompt version found. Please generate a prompt first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if verified data exists
        verified_count = AgenticVerifiedData.objects.filter(project=project).count()
        if verified_count == 0:
            return Response(
                {"error": "No verified data found. Please create verified data first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Run pipeline in background thread
            def run_pipeline():
                pipeline = PipelineService(str(project.id))
                return pipeline.batch_extract_and_compare()

            thread_id = ThreadingService.run_in_background(run_pipeline)

            logger.info(f"Started batch extraction for project {project.id}, thread_id: {thread_id}")

            return Response(
                {
                    "message": "Batch extraction started",
                    "thread_id": thread_id,
                    "project_id": str(project.id),
                    "verified_count": verified_count,
                    "status": "processing",
                    "websocket_url": f"/ws/agentic/projects/{project.id}/progress/",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            logger.error(f"Failed to start batch extraction: {e}")
            return Response(
                {"error": f"Failed to start batch extraction: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="thread-status/<str:thread_id>")
    def thread_status(self, request: Request, pk=None, thread_id=None) -> Response:
        """Get status of a background thread.

        Returns:
        - status: "running", "completed", "error"
        - result: Result data if completed
        - error: Error message if failed
        """
        from .services import ThreadingService

        if not thread_id:
            return Response(
                {"error": "thread_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            thread_status = ThreadingService.get_thread_status(thread_id)
            return Response(thread_status)
        except Exception as e:
            logger.error(f"Failed to get thread status: {e}")
            return Response(
                {"error": f"Failed to get thread status: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="analytics/summary")
    def analytics_summary(self, request: Request, pk=None) -> Response:
        """Get analytics summary for a project with real data."""
        project = self.get_object()

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        # Total documents in project
        total_documents = project.documents.count()

        # Documents that have been processed (have extracted data)
        documents_processed = AgenticExtractedData.objects.filter(
            project=project
        ).values('document').distinct().count()

        # Calculate overall accuracy from comparison results
        if active_prompt:
            comparisons = AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt
            )
            total_fields = comparisons.count()
            matched_fields = comparisons.filter(match=True).count()
            overall_accuracy = (matched_fields / total_fields * 100) if total_fields > 0 else 0
        else:
            total_fields = 0
            matched_fields = 0
            overall_accuracy = 0

        # Documents with verified data
        verified_count = AgenticVerifiedData.objects.filter(project=project).count()

        return Response({
            "total_documents": total_documents,
            "documents_processed": documents_processed,
            "documents_with_verified_data": verified_count,
            "overall_accuracy": round(overall_accuracy, 2),
            "total_fields": total_fields,
            "matched_fields": matched_fields,
            "failed_fields": total_fields - matched_fields,
            "active_prompt_version": active_prompt.version if active_prompt else None,
        })

    @action(detail=True, methods=["get"], url_path="analytics/top-mismatches")
    def analytics_top_mismatches(self, request: Request, pk=None) -> Response:
        """Get top field mismatches for a project with real data."""
        project = self.get_object()
        limit = int(request.query_params.get("limit", 20))

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response({
                "mismatches": [],
                "limit": limit,
                "message": "No active prompt version found",
            })

        # Get fields with most mismatches
        from django.db.models import Count, F

        field_mismatches = (
            AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt,
                match=False
            )
            .values('field_path')
            .annotate(
                mismatch_count=Count('id'),
                # Get most common error type for this field
            )
            .order_by('-mismatch_count')[:limit]
        )

        mismatches = []
        for field in field_mismatches:
            field_path = field['field_path']
            mismatch_count = field['mismatch_count']

            # Get total count for this field (matches + mismatches)
            total_count = AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt,
                field_path=field_path
            ).count()

            # Get most common error type
            most_common_error = (
                AgenticComparisonResult.objects.filter(
                    project=project,
                    prompt_version=active_prompt,
                    field_path=field_path,
                    match=False
                )
                .values('error_type')
                .annotate(count=Count('error_type'))
                .order_by('-count')
                .first()
            )

            # Get example mismatches
            examples = AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt,
                field_path=field_path,
                match=False
            )[:3]

            mismatches.append({
                "field_path": field_path,
                "mismatch_count": mismatch_count,
                "total_count": total_count,
                "accuracy": round(((total_count - mismatch_count) / total_count * 100) if total_count > 0 else 0, 2),
                "most_common_error": most_common_error['error_type'] if most_common_error else None,
                "examples": [
                    {
                        "document_id": str(ex.document.id) if ex.document else None,
                        "document_name": ex.document.original_filename if ex.document else None,
                        "extracted_value": ex.normalized_extracted,
                        "expected_value": ex.normalized_verified,
                        "error_type": ex.error_type,
                    }
                    for ex in examples
                ],
            })

        return Response({
            "mismatches": mismatches,
            "limit": limit,
            "total_found": len(mismatches),
        })

    @action(detail=True, methods=["get"], url_path="analytics/error-types")
    def analytics_error_types(self, request: Request, pk=None) -> Response:
        """Get error type distribution for a project with real data."""
        project = self.get_object()

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response({
                "error_types": {},
                "message": "No active prompt version found",
            })

        # Get error type distribution
        from django.db.models import Count

        error_type_dist = (
            AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt,
                match=False
            )
            .values('error_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Build error type dictionary
        error_types = {}
        total_errors = 0
        for item in error_type_dist:
            error_type = item['error_type'] or 'UNCLASSIFIED'
            count = item['count']
            error_types[error_type] = count
            total_errors += count

        # Add percentage to each error type
        error_types_with_pct = {}
        for error_type, count in error_types.items():
            error_types_with_pct[error_type] = {
                "count": count,
                "percentage": round((count / total_errors * 100) if total_errors > 0 else 0, 2),
            }

        return Response({
            "error_types": error_types_with_pct,
            "total_errors": total_errors,
        })

    @action(detail=True, methods=["get"], url_path="analytics/matrix")
    def analytics_matrix(self, request: Request, pk=None) -> Response:
        """Get mismatch matrix for a project with real data.

        Returns a matrix showing which fields failed for which documents.
        """
        project = self.get_object()

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response({
                "matrix": [],
                "documents": [],
                "fields": [],
                "message": "No active prompt version found",
            })

        # Get all documents with comparison results
        document_ids = (
            AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt
            )
            .values_list('document_id', flat=True)
            .distinct()
        )

        documents = AgenticDocument.objects.filter(id__in=document_ids).order_by('original_filename')

        # Get all unique field paths
        field_paths = (
            AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt
            )
            .values_list('field_path', flat=True)
            .distinct()
            .order_by('field_path')
        )

        # Build matrix: matrix[doc_idx][field_idx] = {"match": bool, "error_type": str}
        matrix = []
        for doc in documents:
            doc_row = []
            for field_path in field_paths:
                # Get comparison result for this doc + field
                comparison = AgenticComparisonResult.objects.filter(
                    project=project,
                    prompt_version=active_prompt,
                    document=doc,
                    field_path=field_path
                ).first()

                if comparison:
                    doc_row.append({
                        "match": comparison.match,
                        "error_type": comparison.error_type,
                        "extracted_value": comparison.normalized_extracted,
                        "expected_value": comparison.normalized_verified,
                    })
                else:
                    doc_row.append(None)  # No data for this field in this document

            matrix.append(doc_row)

        # Prepare document info
        document_info = [
            {
                "id": str(doc.id),
                "name": doc.original_filename,
            }
            for doc in documents
        ]

        # Prepare field info with accuracy stats
        field_info = []
        for field_path in field_paths:
            field_comparisons = AgenticComparisonResult.objects.filter(
                project=project,
                prompt_version=active_prompt,
                field_path=field_path
            )
            total = field_comparisons.count()
            matched = field_comparisons.filter(match=True).count()

            field_info.append({
                "field_path": field_path,
                "total": total,
                "matched": matched,
                "accuracy": round((matched / total * 100) if total > 0 else 0, 2),
            })

        return Response({
            "matrix": matrix,
            "documents": document_info,
            "fields": field_info,
        })

    @action(detail=True, methods=["post"], url_path="analytics/populate")
    def analytics_populate(self, request: Request, pk=None) -> Response:
        """Populate analytics by running comparisons for all documents.

        Compares extracted data with verified data for each document
        and creates comparison results for the matrix view.
        """
        project = self.get_object()

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()
        if not active_prompt:
            return Response(
                {"error": "No active prompt version found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all documents with both extracted and verified data
        documents = project.documents.all()
        comparisons_created = 0

        for doc in documents:
            # Get latest extracted data
            extracted = doc.extracted_data.order_by('-created_at').first()
            # Get verified data
            verified = doc.verified_data.first()

            if not extracted or not verified:
                continue

            extracted_dict = extracted.data if isinstance(extracted.data, dict) else {}
            verified_dict = verified.data if isinstance(verified.data, dict) else {}

            # Compare each field
            all_fields = set(extracted_dict.keys()) | set(verified_dict.keys())

            for field_path in all_fields:
                extracted_value = extracted_dict.get(field_path)
                verified_value = verified_dict.get(field_path)

                # Normalize values for comparison
                normalized_extracted = str(extracted_value).strip() if extracted_value is not None else ""
                normalized_verified = str(verified_value).strip() if verified_value is not None else ""

                match = normalized_extracted == normalized_verified

                # Determine error type
                error_type = None
                if not match:
                    if not normalized_extracted:
                        error_type = "missing"
                    elif not normalized_verified:
                        error_type = "extra"
                    else:
                        error_type = "mismatch"

                # Create or update comparison result
                AgenticComparisonResult.objects.update_or_create(
                    project=project,
                    document=doc,
                    prompt_version=active_prompt,
                    field_path=field_path,
                    defaults={
                        "normalized_extracted": normalized_extracted,
                        "normalized_verified": normalized_verified,
                        "match": match,
                        "error_type": error_type,
                        "organization": project.organization,
                    }
                )
                comparisons_created += 1

        return Response({
            "message": "Analytics populated successfully",
            "comparisons_created": comparisons_created,
        })

    @action(detail=True, methods=["get"], url_path="documents")
    def documents_list(self, request: Request, pk=None) -> Response:
        """List all documents in a project."""
        project = self.get_object()
        documents = project.documents.all().order_by("-uploaded_at")
        serializer = AgenticDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="documents/status")
    def documents_status(self, request: Request, pk=None) -> Response:
        """Get processing status for all documents in a project."""
        project = self.get_object()
        documents = project.documents.all()

        status_list = []
        for doc in documents:
            # Calculate accuracy if both verified and extracted data exist
            accuracy = None
            accuracy_matches = 0
            accuracy_total_fields = 0

            verified_data = doc.verified_data.first()
            extracted_data = doc.extracted_data.first()

            if verified_data and extracted_data and verified_data.data and extracted_data.data:
                # Compare fields between verified and extracted data
                def compare_values(verified, extracted, path=""):
                    nonlocal accuracy_matches, accuracy_total_fields

                    if isinstance(verified, dict):
                        for key, value in verified.items():
                            new_path = f"{path}.{key}" if path else key
                            if key in extracted if isinstance(extracted, dict) else False:
                                compare_values(value, extracted[key], new_path)
                            else:
                                accuracy_total_fields += 1  # Field missing in extracted
                    else:
                        accuracy_total_fields += 1
                        # Compare values (handle type differences)
                        if str(verified).strip() == str(extracted).strip() if extracted is not None else False:
                            accuracy_matches += 1

                compare_values(verified_data.data, extracted_data.data)

                if accuracy_total_fields > 0:
                    accuracy = (accuracy_matches / accuracy_total_fields) * 100

            status_list.append({
                "id": str(doc.id),
                "document_id": str(doc.id),
                "document_name": doc.original_filename,
                "raw_text_status": "complete" if doc.raw_text else "pending",
                "summary_status": "complete" if doc.summaries.exists() else "pending",
                "verified_data_status": "complete" if doc.verified_data.exists() else "pending",
                "extraction_status": "complete" if doc.extracted_data.exists() else "pending",
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "accuracy": accuracy,
                "accuracy_matches": accuracy_matches,
                "accuracy_total_fields": accuracy_total_fields,
            })

        return Response(status_list)

    @action(detail=True, methods=["post"], url_path="documents/upload")
    def documents_upload(self, request: Request, pk=None) -> Response:
        """Upload a document to a project using the same method as prompt studio."""
        from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
        from utils.user_session import UserSessionUtils
        from plugins import get_plugin

        project = self.get_object()
        uploaded_files = request.FILES.getlist("file")

        if not uploaded_files:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_converter_plugin = get_plugin("file_converter")
        documents = []

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            file_data = uploaded_file
            file_type = uploaded_file.content_type
            original_size = uploaded_file.size

            # Convert non-PDF files
            if file_converter_plugin and file_type != "application/pdf":
                file_converter_service = file_converter_plugin["service_class"]()
                file_data, file_name = file_converter_service.process_file(
                    uploaded_file, file_name
                )

            logger.info(f"Uploading file: {file_name}" if file_name else "Uploading file")

            # Get organization and user IDs
            org_id = UserSessionUtils.get_organization_id(request)
            user_id = request.user.user_id

            # Create directory structure (including /extract and /summarize folders)
            from utils.file_storage.constants import FileStorageConstants
            from unstract.core.utilities import UnstractUtils
            from unstract.flags.feature_flag import check_feature_flag_status

            if check_feature_flag_status("sdk1"):
                from unstract.sdk1.file_storage.env_helper import EnvHelper
                from unstract.sdk1.file_storage.constants import StorageType
            else:
                from unstract.sdk.file_storage.env_helper import EnvHelper
                from unstract.sdk.file_storage.constants import StorageType

            from utils.file_storage.constants import FileStorageKeys

            # Get directory path and create folders (like old prompt studio)
            directory_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
                org_id=org_id,
                user_id=user_id,
                tool_id=str(project.id),
                is_create=True,  # This creates /extract and /summarize folders
            )

            # Upload file using PromptStudioFileHelper
            PromptStudioFileHelper.upload_for_ide(
                org_id=org_id,
                user_id=user_id,
                tool_id=str(project.id),
                file_name=file_name,
                file_data=file_data,
            )

            # Build the full storage path (must match what PromptStudioFileHelper creates)
            base_path = UnstractUtils.get_env(
                env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
            )
            # Full path: base_path/org_id/user_id/tool_id/filename
            full_stored_path = f"{base_path}/{org_id}/{user_id}/{str(project.id)}/{file_name}"

            # Extract page count and size for PDFs
            pages = 0  # Default to 0 to avoid NULL constraint
            file_size = original_size  # Default to original
            try:
                if file_type == "application/pdf" or file_name.lower().endswith(".pdf"):
                    import PyPDF2
                    from io import BytesIO

                    # Handle both file objects and bytes
                    if hasattr(file_data, "seek"):
                        file_data.seek(0)
                        pdf_reader = PyPDF2.PdfReader(file_data)
                        pages = len(pdf_reader.pages)
                        file_data.seek(0)  # Reset for potential future use
                    elif isinstance(file_data, bytes):
                        pdf_reader = PyPDF2.PdfReader(BytesIO(file_data))
                        pages = len(pdf_reader.pages)
                        file_size = len(file_data)  # Use actual converted file size
            except Exception as e:
                logger.warning(f"Could not extract page count from PDF: {e}")

            # Create document record with page count
            document = AgenticDocument.objects.create(
                project=project,
                original_filename=file_name,
                stored_path=full_stored_path,  # Use full path matching PromptStudioFileHelper
                size_bytes=file_size,
                pages=pages,
                organization=project.organization,
            )

            documents.append({
                "document_id": str(document.id),
                "document_name": document.original_filename,
                "project_id": str(project.id),
            })

        return Response({"data": documents}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "put"], url_path="settings")
    def update_settings(self, request: Request, pk=None) -> Response:
        """Update project settings including LLM configurations."""
        project = self.get_object()

        # Use serializer for validation and update
        serializer = AgenticProjectSerializer(
            project, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        # Update modified_by before saving
        validated_data = serializer.validated_data
        validated_data["modified_by"] = request.user

        # Save using serializer
        serializer.save()

        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="processing/documents/(?P<document_id>[^/.]+)/extracted-data")
    def get_document_extracted_data(self, request: Request, project_pk=None, document_id=None) -> Response:
        """Get extracted data for a specific document."""
        from prompt_studio.agentic_studio_v2.models import AgenticExtractedData, AgenticDocument

        try:
            document = AgenticDocument.objects.get(id=document_id)
            extracted = AgenticExtractedData.objects.filter(document=document).order_by('-created_at').first()

            if not extracted:
                return Response(
                    {"data": None, "message": "No extraction data found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response({"data": extracted.data})
        except AgenticDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"], url_path="extract/verified")
    def get_all_verified_data(self, request: Request, pk=None) -> Response:
        """Get all verified data for a project."""
        from prompt_studio.agentic_studio_v2.models import AgenticVerifiedData

        project = self.get_object()
        verified_data = AgenticVerifiedData.objects.filter(project=project)

        results = []
        for vd in verified_data:
            results.append({
                "id": str(vd.id),
                "document_id": str(vd.document_id),
                "data": vd.data,
                "created_at": vd.created_at.isoformat() if vd.created_at else None,
                "modified_at": vd.modified_at.isoformat() if vd.modified_at else None,
            })

        return Response(results)

    @action(detail=False, methods=["get"], url_path="extract/verified/(?P<document_id>[^/.]+)")
    def get_document_verified_data(self, request: Request, project_pk=None, document_id=None) -> Response:
        """Get verified data for a specific document."""
        from prompt_studio.agentic_studio_v2.models import AgenticVerifiedData, AgenticDocument

        try:
            document = AgenticDocument.objects.get(id=document_id)
            verified = AgenticVerifiedData.objects.filter(document=document).first()

            if not verified:
                return Response(
                    {"data": None, "message": "No verified data found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response({"data": verified.data})
        except AgenticDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["post"], url_path="extract/verified/(?P<document_id>[^/.]+)/promote")
    def promote_to_verified(self, request: Request, project_pk=None, document_id=None) -> Response:
        """Promote extracted data to verified data."""
        from prompt_studio.agentic_studio_v2.models import (
            AgenticExtractedData, AgenticVerifiedData, AgenticDocument
        )

        try:
            document = AgenticDocument.objects.get(id=document_id)
            extracted = AgenticExtractedData.objects.filter(document=document).order_by('-created_at').first()

            if not extracted:
                return Response(
                    {"error": "No extraction data to promote"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create or update verified data
            verified, created = AgenticVerifiedData.objects.update_or_create(
                document=document,
                defaults={
                    "data": extracted.data,
                    "organization": document.organization,
                }
            )

            return Response({
                "message": "Data promoted to verified",
                "created": created,
            })
        except AgenticDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"], url_path="documents/(?P<document_id>[^/.]+)/comparison")
    def get_document_comparison(self, request: Request, pk=None, document_id=None) -> Response:
        """Get comparison results for a document."""
        from prompt_studio.agentic_studio_v2.models import AgenticComparisonResult, AgenticDocument

        try:
            document = AgenticDocument.objects.get(id=document_id)
            comparisons = AgenticComparisonResult.objects.filter(document=document)

            results = []
            for comp in comparisons:
                results.append({
                    "field_path": comp.field_path,
                    "extracted_value": comp.normalized_extracted,
                    "verified_value": comp.normalized_verified,
                    "match": comp.match,
                    "error_type": comp.error_type if hasattr(comp, 'error_type') else None,
                })

            return Response({"comparisons": results})
        except AgenticDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["post"], url_path="prompts/generate-with-dependencies")
    def generate_prompt_with_dependencies(self, request: Request, pk=None) -> Response:
        """Generate prompt with all dependencies (schema, summaries, etc.)."""
        project = self.get_object()

        # This is a placeholder - actual implementation would trigger the full pipeline
        return Response({
            "message": "Prompt generation started",
            "project_id": str(project.id),
        })


class AgenticDocumentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing documents in Agentic Projects.

    Provides:
    - upload: Handle file upload and trigger processing
    - process_stage: Manually trigger a specific processing stage
    - get_summary: Retrieve document summary
    - get_extracted_data: Retrieve extraction results
    """

    queryset = AgenticDocument.objects.all()
    serializer_class = AgenticDocumentSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter documents by organization and optional project."""
        organization = UserContext.get_organization()
        queryset = AgenticDocument.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        # Filter by project if provided
        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-uploaded_at")

    @action(detail=False, methods=["post"])
    def upload(self, request: Request) -> Response:
        """Handle file upload and trigger async processing.

        Expected request data:
        - project_id: UUID of the project
        - file: Uploaded file (PDF, image, etc.)
        """
        project_id = request.data.get("project_id")
        file = request.FILES.get("file")

        if not project_id or not file:
            return Response(
                {"error": "project_id and file are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # TODO: Store file using AgenticStudioFileHelper
        # TODO: Create document record
        # TODO: Trigger async processing task

        return Response(
            {
                "message": "File uploaded successfully",
                # "document_id": str(document.id),
                # "processing_job_id": job.id,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="file")
    def get_file(self, request: Request, pk=None) -> Response:
        """Serve the actual PDF file for viewing.

        Returns the PDF file binary data with appropriate headers.
        """
        from django.http import FileResponse, Http404
        from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
        from utils.user_session import UserSessionUtils
        import os

        document = self.get_object()

        try:
            from utils.file_storage.constants import FileStorageKeys, FileStorageConstants
            from pathlib import Path
            from unstract.core.utilities import UnstractUtils
            from unstract.flags.feature_flag import check_feature_flag_status

            if check_feature_flag_status("sdk1"):
                from unstract.sdk1.file_storage.env_helper import EnvHelper
                from unstract.sdk1.file_storage.constants import StorageType
            else:
                from unstract.sdk.file_storage.env_helper import EnvHelper
                from unstract.sdk.file_storage.constants import StorageType

            # Get organization and user info
            org_id = UserSessionUtils.get_organization_id(request)
            user_id = request.user.user_id
            project_id = str(document.project.id)
            file_name = document.original_filename

            logger.info(f"Fetching PDF file: {file_name} for document {document.id}")

            # Get file storage instance
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )

            # Construct file path
            base_path = UnstractUtils.get_env(
                env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
            )
            file_path = str(Path(base_path) / org_id / user_id / project_id / file_name)

            # Read file content
            file_content = fs_instance.read(file_path, mode="rb")

            if not file_content:
                logger.error(f"File not found in storage: {file_name}")
                raise Http404("Document file not found in storage")

            # Create response with file content
            from io import BytesIO
            file_obj = BytesIO(file_content)

            # Determine content type
            content_type = 'application/pdf'
            if file_name.lower().endswith('.png'):
                content_type = 'image/png'
            elif file_name.lower().endswith('.jpg') or file_name.lower().endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_name.lower().endswith('.gif'):
                content_type = 'image/gif'

            response = FileResponse(file_obj, content_type=content_type)
            response['Content-Disposition'] = f'inline; filename="{file_name}"'
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type'

            return response

        except Exception as e:
            logger.error(f"Error serving document file: {e}")
            raise Http404(f"Failed to retrieve document file: {str(e)}")

    @action(detail=True, methods=["post"])
    def process_stage(self, request: Request, pk=None) -> Response:
        """Manually trigger a specific processing stage (SYNCHRONOUS).

        Request body:
        - stage: One of 'raw_text', 'summary', 'extraction', 'provisional_verified' (or 'verified_data' as alias)

        Returns:
        - 200 OK with processing results
        """
        import requests

        document = self.get_object()
        stage = request.data.get("stage")

        # Map verified_data alias to provisional_verified for backwards compatibility
        if stage == "verified_data":
            stage = "provisional_verified"

        if stage not in ["raw_text", "summary", "extraction", "provisional_verified"]:
            return Response(
                {"error": "Invalid stage. Must be 'raw_text', 'summary', 'extraction', 'provisional_verified', or 'verified_data'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate prerequisites
        project = document.project
        organization = UserContext.get_organization()

        if stage == "raw_text":
            if not project.llmwhisperer_id:
                return Response(
                    {"error": "No LLMWhisperer configured for this project. Please configure in Settings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif stage == "summary":
            if not document.raw_text:
                return Response(
                    {"error": "Document has no raw_text. Please process raw_text stage first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not project.agent_llm_id:
                return Response(
                    {"error": "No Agent LLM configured for this project. Please configure in Settings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif stage == "extraction":
            if not document.raw_text:
                return Response(
                    {"error": "Document has no raw_text. Please process raw_text stage first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not project.extractor_llm_id:
                return Response(
                    {"error": "No Extractor LLM configured for this project. Please configure in Settings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get prompt service URL
        prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
        prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
        prompt_service_url = f"{prompt_host}:{prompt_port}"

        # Get platform key for authentication with platform-service
        from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
        platform_key = PlatformAuthenticationService.get_active_platform_key()
        headers = {
            "X-Platform-Key": str(platform_key.key) if platform_key else "",
        }

        try:
            if stage == "raw_text":
                # Get organization and user IDs
                org_id = str(organization.organization_id)
                user_id = str(request.user.user_id)

                # Build output file path for extracted text (X2Text will write it)
                from utils.file_storage.constants import FileStorageConstants
                from unstract.core.utilities import UnstractUtils
                import os

                base_path = UnstractUtils.get_env(
                    env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
                )
                # Path: base_path/org_id/user_id/tool_id/extract/filename.txt
                file_name_without_ext = os.path.splitext(document.original_filename)[0]
                output_file_path = f"{base_path}/{org_id}/{user_id}/{str(project.id)}/extract/{file_name_without_ext}.txt"

                # Call prompt-service to extract raw text
                payload = {
                    "document_id": str(document.id),
                    "project_id": str(project.id),
                    "file_path": document.stored_path,
                    "organization_id": str(organization.organization_id),
                    "adapter_instance_id": str(project.llmwhisperer_id),
                    "output_file_path": output_file_path,  # X2Text will write file here
                }

                response = requests.post(
                    f"{prompt_service_url}/agentic/extract-text",
                    json=payload,
                    headers=headers,
                    timeout=300,
                )

                if response.status_code != 200:
                    return Response(
                        {"error": f"Text extraction failed: {response.text}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                extraction_data = response.json()
                raw_text = extraction_data.get("raw_text", "")
                document.raw_text = raw_text

                # X2Text already wrote the file to output_file_path (like old prompt studio)
                # No need to write it again here

                # Update status to indicate raw text is ready
                document.status = "raw_text_ready"
                # Pages already extracted during upload with PyPDF2
                # Don't overwrite unless explicitly returned (which it won't be)
                document.save()

                return Response(
                    {
                        "message": "Raw text extracted successfully",
                        "document_id": str(document.id),
                        "pages": document.pages,
                        "status": document.status,
                    },
                    status=status.HTTP_200_OK,
                )

            elif stage == "summary":
                # Call prompt-service to summarize
                payload = {
                    "document_id": str(document.id),
                    "project_id": str(project.id),
                    "document_text": document.raw_text or "",
                    "organization_id": str(organization.organization_id),
                    "adapter_instance_id": str(project.agent_llm_id),
                }

                response = requests.post(
                    f"{prompt_service_url}/agentic/summarize",
                    json=payload,
                    headers=headers,
                    timeout=300,
                )

                if response.status_code != 200:
                    return Response(
                        {"error": f"Summarization failed: {response.text}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                summary_data = response.json()
                AgenticSummary.objects.update_or_create(
                    project=project,
                    document=document,
                    defaults={
                        "summary_text": summary_data.get("summary_text", ""),
                        "organization": organization,
                    },
                )

                return Response(
                    {
                        "message": "Summary generated successfully",
                        "document_id": str(document.id),
                        "summary": summary_data,
                    },
                    status=status.HTTP_200_OK,
                )

            elif stage == "extraction":
                # Get active prompt
                active_prompt = project.prompt_versions.filter(is_active=True).first()
                if not active_prompt:
                    return Response(
                        {"error": "No active prompt version found. Please generate a prompt first."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Call prompt-service to extract
                payload = {
                    "document_id": str(document.id),
                    "project_id": str(project.id),
                    "document_text": document.raw_text or "",
                    "prompt_text": active_prompt.prompt_text,
                    "organization_id": str(organization.organization_id),
                    "adapter_instance_id": str(project.extractor_llm_id),
                }

                response = requests.post(
                    f"{prompt_service_url}/agentic/extract",
                    json=payload,
                    headers=headers,
                    timeout=300,
                )

                if response.status_code != 200:
                    return Response(
                        {"error": f"Extraction failed: {response.text}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                extraction_data = response.json()
                AgenticExtractedData.objects.update_or_create(
                    project=project,
                    document=document,
                    prompt_version=active_prompt,
                    defaults={
                        "data": extraction_data.get("extracted_data", {}),
                        "organization": organization,
                    },
                )

                return Response(
                    {
                        "message": "Extraction completed successfully",
                        "document_id": str(document.id),
                        "data": extraction_data,
                    },
                    status=status.HTTP_200_OK,
                )

            elif stage == "provisional_verified":
                # Generate provisional verified data using PipelineService
                from .services import PipelineService

                try:
                    pipeline = PipelineService(str(project.id))
                    verified_data = pipeline.generate_provisional_verified_data(document)

                    return Response(
                        {
                            "message": "Provisional verified data generated successfully",
                            "document_id": str(document.id),
                            "verified_data_id": str(verified_data.id),
                            "data": verified_data.data,
                        },
                        status=status.HTTP_200_OK,
                    )
                except Exception as e:
                    logger.error(f"Error generating provisional verified data: {e}")
                    return Response(
                        {"error": f"Failed to generate provisional verified data: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling prompt-service: {e}")
            return Response(
                {"error": f"Failed to communicate with prompt-service: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"Error processing stage {stage}: {e}")
            return Response(
                {"error": f"Processing failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="processing/state")
    def get_processing_state(self, request: Request) -> Response:
        """Get processing state for all documents in the project.

        Returns real-time status of all pipeline stages for each document.
        """
        from prompt_studio.agentic_studio_v2.services.state_manager import ProcessingStateManager

        # Get project from query params
        project_id = request.query_params.get("project_id")
        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            state_mgr = ProcessingStateManager()
            pipeline_status = state_mgr.get_pipeline_status(project_id=UUID(project_id))

            return Response(pipeline_status, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Failed to get processing state: {e}")
            return Response(
                {"error": f"Failed to get processing state: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Old synchronous version removed - now using async Celery tasks above
    # The rest of the old synchronous code has been deleted
    @action(detail=True, methods=["get"], url_path="summary")
    def get_summary(self, request: Request, pk=None, project_pk=None) -> Response:
        """Get summary for a document."""
        document = self.get_object()
        summary = AgenticSummary.objects.filter(document=document).first()

        if not summary:
            return Response(
                {"summary": None, "message": "No summary found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"summary_text": summary.summary_text})

    @action(detail=True, methods=["get"], url_path="verified-data")
    def get_verified_data(self, request: Request, pk=None, project_pk=None) -> Response:
        """Get verified data for a document."""
        document = self.get_object()
        verified = AgenticVerifiedData.objects.filter(document=document).first()

        if not verified:
            return Response(
                {"data": None, "message": "No verified data found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"data": verified.data})

    @action(detail=True, methods=["get"], url_path="extraction-data")
    def get_extraction_data(self, request: Request, pk=None, project_pk=None) -> Response:
        """Get extraction data for a document."""
        document = self.get_object()
        extraction = AgenticExtractedData.objects.filter(document=document).first()

        if not extraction:
            return Response(
                {"data": None, "message": "No extraction data found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"data": extraction.data})

    @action(detail=True, methods=["get"], url_path="raw-text")
    def get_raw_text(self, request: Request, pk=None, project_pk=None) -> Response:
        """Get raw text for a document.

        Reads from /extract folder like old prompt studio does.

        Returns:
            Response with raw_text field
        """
        document = self.get_object()
        project = document.project
        organization = UserContext.get_organization()

        # Get organization and user IDs
        org_id = str(organization.organization_id)
        user_id = str(request.user.user_id)

        # Build path to extract file: base_path/org_id/user_id/tool_id/extract/filename.txt
        from utils.file_storage.constants import FileStorageConstants, FileStorageKeys
        from unstract.core.utilities import UnstractUtils
        from unstract.flags.feature_flag import check_feature_flag_status
        import os

        if check_feature_flag_status("sdk1"):
            from unstract.sdk1.file_storage.env_helper import EnvHelper
            from unstract.sdk1.file_storage.constants import StorageType
        else:
            from unstract.sdk.file_storage.env_helper import EnvHelper
            from unstract.sdk.file_storage.constants import StorageType

        base_path = UnstractUtils.get_env(
            env_key=FileStorageConstants.REMOTE_PROMPT_STUDIO_FILE_PATH
        )

        # Build extract file path
        file_name_without_ext = os.path.splitext(document.original_filename)[0]
        extract_file_path = f"{base_path}/{org_id}/{user_id}/{str(project.id)}/extract/{file_name_without_ext}.txt"

        # Try to read from file first (like old prompt studio)
        raw_text = ""
        try:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
            raw_text = fs_instance.read(path=extract_file_path, mode="r")
        except FileNotFoundError:
            # Fallback to database field if file not found
            raw_text = document.raw_text or ""

        return Response({
            "raw_text": raw_text,
            "pages": document.pages,
        })


class AgenticSchemaViewSet(viewsets.ModelViewSet):
    """ViewSet for managing extraction schemas."""

    queryset = AgenticSchema.objects.all()
    serializer_class = AgenticSchemaSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter schemas by organization and optional project."""
        organization = UserContext.get_organization()
        queryset = AgenticSchema.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-created_at")

    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        """Trigger schema generation from document summaries (async via Celery).

        Request body:
        - project_id: UUID of the project

        Returns:
        - 202 Accepted with task_id for tracking
        - Use GET /processing/state endpoint to check progress
        """
        from prompt_studio.agentic_studio_v2.tasks import generate_schema_task
        from prompt_studio.agentic_studio_v2.services.state_manager import ProcessingStateManager

        project_id = request.data.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get project
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if summaries exist
        from .models import AgenticSummary
        summaries_count = AgenticSummary.objects.filter(project_id=project_id).count()

        if summaries_count == 0:
            return Response(
                {"error": "No summaries found for this project. Please process documents first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Set initial pending status
            state_mgr = ProcessingStateManager()
            state_mgr.set_stage_status(
                project_id=project.id,
                stage="schema",
                status="pending",
                progress=0,
                message=f"Queued for schema generation from {summaries_count} summaries..."
            )

            # Enqueue Celery task
            task = generate_schema_task.delay(str(project_id))

            logger.info(f"Enqueued schema generation for project {project_id}, task_id: {task.id}")

            return Response(
                {
                    "message": "Schema generation started",
                    "task_id": task.id,
                    "project_id": str(project_id),
                    "summaries_count": summaries_count,
                    "status": "processing",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            logger.error(f"Failed to enqueue schema generation task: {e}")
            return Response(
                {"error": f"Failed to start schema generation: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AgenticVerifiedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for managing verified/ground truth data."""

    queryset = AgenticVerifiedData.objects.all()
    serializer_class = AgenticVerifiedDataSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization and optional project/document."""
        organization = UserContext.get_organization()
        queryset = AgenticVerifiedData.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        return queryset

    @action(detail=True, methods=["post"], url_path="generate")
    def generate_verified_data(self, request: Request, pk=None, **kwargs) -> Response:
        """Generate verified data using LLM from extracted data.

        This is Phase 4: Generate Verified Data
        - Gets extracted data for the document
        - Calls VerifierAgent via prompt-service
        - Creates/updates verified data record
        """
        import requests
        from django.conf import settings

        # pk is document_id in this case (from nested route)
        document_id = pk
        # project_pk comes from nested route URL kwargs
        project_id = kwargs.get('project_pk') or self.kwargs.get('project_pk')

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get project
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # Get document
            document = AgenticDocument.objects.get(id=document_id, project=project)
        except AgenticDocument.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check prerequisites
        if not project.agent_llm_id:
            return Response(
                {"error": "No Agent LLM configured. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get extracted data (most recent for this document)
        try:
            # Debug: Check what extracted data exists
            all_extractions = AgenticExtractedData.objects.filter(
                project=project,
                document=document
            ).values_list('id', 'prompt_version_id', 'created_at')
            logger.info(f"Found {len(all_extractions)} extracted data records for document {document.id}: {list(all_extractions)}")

            extracted_data_obj = AgenticExtractedData.objects.filter(
                project=project,
                document=document
            ).order_by('-created_at').first()

            if not extracted_data_obj:
                # Provide helpful error message
                prompt_exists = AgenticPromptVersion.objects.filter(project=project, is_active=True).exists()
                error_msg = "No extracted data found for this document. "
                if not prompt_exists:
                    error_msg += "Please generate a prompt first, then run extraction."
                else:
                    error_msg += "Please run extraction on this document using the Extracted Data tab."

                logger.warning(f"No extracted data for document {document.id} in project {project.id}")
                return Response(
                    {"error": error_msg},
                    status=status.HTTP_404_NOT_FOUND,
                )

            logger.info(f"Using extracted data {extracted_data_obj.id} from prompt_version {extracted_data_obj.prompt_version_id}")
            extracted_data = extracted_data_obj.data
        except Exception as e:
            logger.error(f"Error fetching extracted data: {e}")
            return Response(
                {"error": f"Error fetching extracted data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Get document raw text
        if not document.raw_text:
            return Response(
                {"error": "Document raw text not available"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get schema (optional) - use filter().first() to handle multiple schemas
        schema_data = None
        schema_obj = AgenticSchema.objects.filter(
            project=project, is_active=True
        ).first()
        if schema_obj:
            schema_data = schema_obj.json_schema

        # Call prompt-service generate-verified endpoint
        prompt_service_url = f"{settings.PROMPT_HOST}:{settings.PROMPT_PORT}"
        platform_key_obj = PlatformAuthenticationService.get_active_platform_key(
            organization_id=str(organization.organization_id)
        )

        payload = {
            "project_id": str(project.id),
            "document_id": str(document.id),
            "document_text": document.raw_text,
            "extracted_data": extracted_data,
            "schema": schema_data,
            "organization_id": str(organization.organization_id),
            "adapter_instance_id": str(project.agent_llm_id),
        }

        try:
            response = requests.post(
                f"{prompt_service_url}/agentic/generate-verified",
                json=payload,
                headers={"X-Platform-Key": str(platform_key_obj.key)},
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Prompt service call failed: {e}")
            return Response(
                {"error": f"Failed to generate verified data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create or update verified data
        verified_data, created = AgenticVerifiedData.objects.update_or_create(
            project=project,
            document=document,
            defaults={
                "organization": organization,
                "data": result.get("data", {}),
            }
        )

        logger.info(f"{'Created' if created else 'Updated'} verified data for document {document.id}")

        serializer = self.get_serializer(verified_data)
        return Response(
            {
                **serializer.data,
                "verification_notes": result.get("verification_notes"),
                "generated": True,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AgenticPromptVersionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing prompt versions."""

    queryset = AgenticPromptVersion.objects.all()
    serializer_class = AgenticPromptVersionSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization and optional project."""
        organization = UserContext.get_organization()
        queryset = AgenticPromptVersion.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-version")

    @action(detail=True, methods=["post"])
    def set_active(self, request: Request, pk=None) -> Response:
        """Set this prompt version as the active one."""
        prompt_version = self.get_object()

        # Deactivate all other versions for this project
        AgenticPromptVersion.objects.filter(project=prompt_version.project).update(
            is_active=False
        )

        # Activate this version
        prompt_version.is_active = True
        prompt_version.save()

        return Response(
            {
                "message": f"Prompt version {prompt_version.version} is now active",
                "version_id": str(prompt_version.id),
            }
        )

    def list_for_project(self, request: Request, project_pk=None) -> Response:
        """List all prompt versions for a specific project (prompt history).

        This endpoint is called by the frontend as:
        GET /projects/{project_id}/prompts/

        Returns a list of all prompt versions ordered by version (newest first).
        """
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate project exists and user has access
        try:
            project = AgenticProject.objects.get(
                id=project_pk, organization=organization
            )
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get all prompt versions for this project
        prompts = AgenticPromptVersion.objects.filter(
            project=project, organization=organization
        ).order_by("-version")

        serializer = self.get_serializer(prompts, many=True)
        return Response(serializer.data)

    def get_latest(self, request: Request, project_pk=None) -> Response:
        """Get the latest prompt version for a project.

        This endpoint is called by the frontend as:
        GET /projects/{project_id}/prompts/latest/

        Returns the most recent prompt version (highest version number).
        """
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate project exists and user has access
        try:
            project = AgenticProject.objects.get(
                id=project_pk, organization=organization
            )
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get the latest prompt version
        latest_prompt = (
            AgenticPromptVersion.objects.filter(
                project=project, organization=organization
            )
            .order_by("-version")
            .first()
        )

        if not latest_prompt:
            return Response(
                {"error": "No prompts found for this project"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(latest_prompt)
        return Response(serializer.data)

    def get_by_version(self, request: Request, project_pk=None, version=None) -> Response:
        """Get a specific prompt version by version number.

        This endpoint is called by the frontend as:
        GET /projects/{project_id}/prompts/{version}/

        Returns the prompt with the specified version number.
        """
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate project exists and user has access
        try:
            project = AgenticProject.objects.get(
                id=project_pk, organization=organization
            )
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get the prompt with the specified version
        try:
            prompt = AgenticPromptVersion.objects.get(
                project=project, organization=organization, version=version
            )
        except AgenticPromptVersion.DoesNotExist:
            return Response(
                {"error": f"Prompt version {version} not found for this project"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(prompt)
        return Response(serializer.data)


class AgenticExtractionViewSet(viewsets.ViewSet):
    """ViewSet for extraction operations (not a model ViewSet)."""

    @action(detail=False, methods=["post"])
    def run_extraction(self, request: Request) -> Response:
        """Run extraction on all documents with verified data.

        Request body:
        - project_id: UUID of the project
        - prompt_version_id: Optional UUID of specific prompt version
        """
        project_id = request.data.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Trigger batch extraction task

        return Response(
            {"message": "Batch extraction started", "project_id": project_id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"])
    def compare_results(self, request: Request) -> Response:
        """Compare extracted data vs verified data.

        Request body:
        - project_id: UUID of the project
        - document_id: Optional UUID of specific document to compare
        - use_llm_classification: Optional boolean to use LLM for error classification
        """
        import requests
        from django.conf import settings

        project_id = request.data.get("project_id")
        document_id = request.data.get("document_id")
        use_llm_classification = request.data.get("use_llm_classification", False)

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get organization
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get project
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get lightweight LLM adapter if using LLM classification
        lightweight_llm_adapter = None
        if use_llm_classification and project.lightweight_llm_id:
            lightweight_llm_adapter = str(project.lightweight_llm_id)

        try:
            # Get extracted data and verified data
            from .models import AgenticExtractedData, AgenticVerifiedData

            if document_id:
                # Compare specific document
                extracted = AgenticExtractedData.objects.filter(
                    project=project,
                    document_id=document_id
                ).first()
                verified = AgenticVerifiedData.objects.filter(
                    project=project,
                    document_id=document_id
                ).first()

                if not extracted or not verified:
                    return Response(
                        {"error": "Extracted or verified data not found for this document"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                documents_to_compare = [(extracted, verified)]
            else:
                # Compare all documents with verified data
                verified_docs = AgenticVerifiedData.objects.filter(project=project)
                documents_to_compare = []

                for verified in verified_docs:
                    extracted = AgenticExtractedData.objects.filter(
                        project=project,
                        document=verified.document
                    ).first()
                    if extracted:
                        documents_to_compare.append((extracted, verified))

            if not documents_to_compare:
                return Response(
                    {"error": "No documents found for comparison"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Call prompt-service to compare each document
            prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
            prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
            prompt_service_url = f"{prompt_host}:{prompt_port}"

            all_results = []

            for extracted, verified in documents_to_compare:
                payload = {
                    "project_id": str(project_id),
                    "document_id": str(extracted.document.id),
                    "extracted_data": extracted.data,
                    "verified_data": verified.data,
                    "use_llm_classification": use_llm_classification,
                    "lightweight_llm_adapter": lightweight_llm_adapter,
                    "organization_id": str(organization.organization_id),
                }

                response = requests.post(
                    f"{prompt_service_url}/agentic/compare",
                    json=payload,
                    timeout=300,
                )

                if response.status_code != 200:
                    logger.error(f"Comparison failed for document {extracted.document.id}: {response.text}")
                    continue

                comparison_data = response.json()

                # Save comparison results
                from .models import AgenticComparisonResult

                # Delete old results for this document
                AgenticComparisonResult.objects.filter(
                    project=project,
                    document=extracted.document
                ).delete()

                # Create new results
                for field_result in comparison_data.get("field_results", []):
                    AgenticComparisonResult.objects.create(
                        project=project,
                        prompt_version=extracted.prompt_version,
                        document=extracted.document,
                        field_path=field_result.get("field_path"),
                        normalized_extracted=field_result.get("extracted_value"),
                        normalized_verified=field_result.get("expected_value"),
                        match=field_result.get("is_match", False),
                        error_type=field_result.get("error_type"),
                        organization=organization,
                    )

                all_results.append(comparison_data)

            # Calculate overall accuracy
            total_fields = sum(r.get("total_fields", 0) for r in all_results)
            matched_fields = sum(r.get("matched_fields", 0) for r in all_results)
            overall_accuracy = (matched_fields / total_fields * 100) if total_fields > 0 else 0

            return Response(
                {
                    "message": "Comparison completed",
                    "project_id": project_id,
                    "documents_compared": len(all_results),
                    "overall_accuracy": round(overall_accuracy, 2),
                    "total_fields": total_fields,
                    "matched_fields": matched_fields,
                    "results": all_results,
                },
                status=status.HTTP_200_OK,
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling prompt-service: {e}")
            return Response(
                {"error": f"Failed to communicate with prompt-service: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"Error comparing results: {e}")
            return Response(
                {"error": f"Comparison failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AgenticTuningViewSet(viewsets.ViewSet):
    """ViewSet for prompt tuning operations."""

    @action(detail=False, methods=["post"])
    def tune_field(self, request: Request) -> Response:
        """Tune a specific failing field.

        Request body:
        - project_id: UUID of the project
        - field_path: Dot-separated field path (e.g., 'customer.name')
        - error_type: Optional error type classification
        """
        import requests
        from django.conf import settings

        project_id = request.data.get("project_id")
        field_path = request.data.get("field_path")
        error_type = request.data.get("error_type")

        if not project_id or not field_path:
            return Response(
                {"error": "project_id and field_path are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get organization
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get project
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get Agent LLM adapter (used for prompt tuning agents)
        adapter_id = None
        if project.agent_llm_id:
            adapter_id = str(project.agent_llm_id)

        if not adapter_id:
            return Response(
                {"error": "No Agent LLM configured for this project. Please configure Agent LLM in Settings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()
        if not active_prompt:
            return Response(
                {"error": "No active prompt version found for this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get schema
        schema = AgenticSchema.objects.filter(project=project).first()
        if not schema:
            return Response(
                {"error": "No schema found for this project. Please generate schema first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get comparison results for this field to find failures
            from .models import AgenticComparisonResult
            comparison_results = AgenticComparisonResult.objects.filter(
                project=project,
                field_path=field_path,
                match=False,
            )

            failures = []
            for result in comparison_results[:10]:  # Limit to 10 examples
                failures.append({
                    "document_id": str(result.document.id) if result.document else None,
                    "extracted_value": result.normalized_extracted,
                    "expected_value": result.normalized_verified,
                })

            # Call prompt-service to tune the field
            prompt_host = getattr(settings, 'PROMPT_HOST', 'http://unstract-prompt-service')
            prompt_port = getattr(settings, 'PROMPT_PORT', 3003)
            prompt_service_url = f"{prompt_host}:{prompt_port}"

            payload = {
                "project_id": str(project_id),
                "field_path": field_path,
                "current_prompt": active_prompt.prompt_text,
                "schema": schema.json_schema,
                "failures": failures,
                "error_type": error_type,
                "organization_id": str(organization.organization_id),
                "adapter_instance_id": adapter_id,
            }

            response = requests.post(
                f"{prompt_service_url}/agentic/tune-field",
                json=payload,
                timeout=600,  # Tuning can take longer
            )

            if response.status_code != 200:
                return Response(
                    {"error": f"Field tuning failed: {response.text}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            tuning_result = response.json()

            # Create new prompt version if tuning was successful
            if tuning_result.get("success"):
                new_version = AgenticPromptVersion.objects.create(
                    project=project,
                    prompt_text=tuning_result.get("tuned_prompt"),
                    version=active_prompt.version + 1,
                    is_active=False,  # Don't auto-activate, let user review
                    organization=organization,
                )

                return Response(
                    {
                        "message": f"Tuning completed for field: {field_path}",
                        "project_id": project_id,
                        "field_path": field_path,
                        "new_prompt_version_id": str(new_version.id),
                        "explanation": tuning_result.get("explanation"),
                        "iterations": tuning_result.get("iterations", 0),
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "message": f"Tuning failed for field: {field_path}",
                        "project_id": project_id,
                        "field_path": field_path,
                        "explanation": tuning_result.get("explanation"),
                    },
                    status=status.HTTP_200_OK,
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling prompt-service: {e}")
            return Response(
                {"error": f"Failed to communicate with prompt-service: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.error(f"Error tuning field: {e}")
            return Response(
                {"error": f"Field tuning failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"])
    def field_accuracy(self, request: Request) -> Response:
        """Get per-field accuracy breakdown.

        Query params:
        - project_id: UUID of the project
        """
        project_id = request.query_params.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            return Response(
                {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Get active prompt version
        active_prompt = project.prompt_versions.filter(is_active=True).first()

        if not active_prompt:
            return Response(
                {"message": "No active prompt version found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Calculate per-field accuracy
        comparisons = AgenticComparisonResult.objects.filter(
            project=project, prompt_version=active_prompt
        )

        field_stats = []
        for field_path in comparisons.values_list("field_path", flat=True).distinct():
            field_comparisons = comparisons.filter(field_path=field_path)
            total = field_comparisons.count()
            matched = field_comparisons.filter(match=True).count()
            failed = total - matched

            # Get most common error type for this field
            error_types = field_comparisons.exclude(match=True).values(
                "error_type"
            ).annotate(count=Count("error_type")).order_by("-count")
            most_common_error = error_types.first()["error_type"] if error_types else None

            field_stats.append(
                {
                    "field_path": field_path,
                    "total": total,
                    "matched": matched,
                    "failed": failed,
                    "accuracy": round((matched / total * 100) if total > 0 else 0, 2),
                    "most_common_error": most_common_error,
                }
            )

        # Sort by accuracy (ascending, so failing fields first)
        field_stats.sort(key=lambda x: x["accuracy"])

        return Response(
            {
                "project_id": project_id,
                "prompt_version": active_prompt.version,
                "fields": field_stats,
            }
        )


class AgenticAnalyticsViewSet(viewsets.ViewSet):
    """ViewSet for analytics and reporting."""

    @action(detail=False, methods=["get"])
    def accuracy_trends(self, request: Request) -> Response:
        """Get accuracy trends over prompt versions.

        Query params:
        - project_id: UUID of the project
        """
        project_id = request.query_params.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prompt_versions = (
            AgenticPromptVersion.objects.filter(project_id=project_id)
            .order_by("version")
            .values("version", "accuracy", "created_at", "short_desc")
        )

        return Response(
            {"project_id": project_id, "versions": list(prompt_versions)}
        )

    @action(detail=False, methods=["get"])
    def mismatch_matrix(self, request: Request) -> Response:
        """Get field-level mismatch heatmap data.

        Query params:
        - project_id: UUID of the project
        """
        project_id = request.query_params.get("project_id")

        if not project_id:
            return Response(
                {"error": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Build matrix of document vs field with match/mismatch indicators

        return Response({"project_id": project_id, "matrix": []})


class AgenticExtractionNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for extraction notes."""

    queryset = AgenticExtractionNote.objects.all()
    serializer_class = AgenticExtractionNoteSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Filter by organization and optional filters."""
        organization = UserContext.get_organization()
        queryset = AgenticExtractionNote.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset


class AgenticSummaryViewSet(viewsets.ModelViewSet):
    """ViewSet for document summaries."""

    queryset = AgenticSummary.objects.all()
    serializer_class = AgenticSummarySerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization."""
        organization = UserContext.get_organization()
        if organization:
            return AgenticSummary.objects.filter(organization=organization)
        return AgenticSummary.objects.none()


class AgenticExtractedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for extracted data."""

    queryset = AgenticExtractedData.objects.all()
    serializer_class = AgenticExtractedDataSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization."""
        organization = UserContext.get_organization()
        if organization:
            return AgenticExtractedData.objects.filter(organization=organization)
        return AgenticExtractedData.objects.none()


class AgenticComparisonResultViewSet(viewsets.ModelViewSet):
    """ViewSet for comparison results."""

    queryset = AgenticComparisonResult.objects.all()
    serializer_class = AgenticComparisonResultSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization."""
        organization = UserContext.get_organization()
        if organization:
            return AgenticComparisonResult.objects.filter(
                organization=organization
            )
        return AgenticComparisonResult.objects.none()


class AgenticLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for logs (read-only)."""

    queryset = AgenticLog.objects.all()
    serializer_class = AgenticLogSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization and optional project."""
        organization = UserContext.get_organization()
        queryset = AgenticLog.objects.all()

        if organization:
            queryset = queryset.filter(organization=organization)

        project_id = self.request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-timestamp")


class AgenticSettingViewSet(viewsets.ModelViewSet):
    """ViewSet for system settings."""

    queryset = AgenticSetting.objects.all()
    serializer_class = AgenticSettingSerializer
    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def get_queryset(self):
        """Filter by organization."""
        organization = UserContext.get_organization()
        if organization:
            return AgenticSetting.objects.filter(organization=organization)
        return AgenticSetting.objects.none()


class AgenticConnectorViewSet(viewsets.ViewSet):
    """ViewSet for listing available LLM adapters/connectors."""

    versioning_class = URLPathVersioning
    permission_classes = [IsOrganizationMember]

    def list(self, request: Request) -> Response:
        """List all available LLM adapters for the organization."""
        from adapter_processor_v2.models import AdapterInstance

        organization = UserContext.get_organization()
        if not organization:
            return Response({"connectors": []})

        # Get all adapters for the organization
        adapters = AdapterInstance.objects.filter(
            organization=organization
        )

        connectors = []
        for adapter in adapters:
            connector_data = {
                "id": str(adapter.id),
                "name": adapter.adapter_name,
                "type": adapter.adapter_type.adapter_name if adapter.adapter_type else "Unknown",
                "provider": adapter.adapter_metadata.get("adapter_id", "") if adapter.adapter_metadata else "",
                "model": adapter.adapter_metadata.get("model", "") if adapter.adapter_metadata else "",
                "description": adapter.description or "",
            }
            connectors.append(connector_data)

        return Response(connectors)


# Server-Sent Events endpoint for real-time pipeline updates
@api_view(["GET"])
@permission_classes([IsOrganizationMember])
def pipeline_events(request: Request, project_id: str):
    """Stream pipeline progress events via Server-Sent Events.

    This endpoint keeps the connection open and streams updates
    about pipeline processing stages.
    """

    def event_stream():
        """Generate SSE formatted events."""
        # TODO: Integrate with Redis pub/sub for real-time updates
        # For now, send a test event
        yield f"data: {{'stage': 'raw_text', 'status': 'in_progress', 'progress': 50}}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["GET", "POST"])
@permission_classes([IsOrganizationMember])
def connectors_list(request: Request):
    """List or create connectors (LLM adapters).

    GET: Returns list of adapter instances that can be used for processing.
    POST: Creates a new adapter instance with simplified interface.
    """
    from adapter_processor_v2.models import AdapterInstance

    organization = UserContext.get_organization()
    if not organization:
        return Response([], status=status.HTTP_200_OK if request.method == "GET" else status.HTTP_400_BAD_REQUEST)

    if request.method == "GET":
        # Get all adapters for the organization
        adapters = AdapterInstance.objects.filter(
            organization=organization
        )

        connectors = []
        for adapter in adapters:
            connector_data = {
                "id": str(adapter.id),
                "name": adapter.adapter_name,
                "type": adapter.adapter_type if adapter.adapter_type else "LLM",
                "provider": adapter.adapter_id or "",
                "model": adapter.adapter_metadata.get("model", "") if adapter.adapter_metadata else "",
                "description": adapter.description or "",
            }
            connectors.append(connector_data)

        return Response(connectors)

    elif request.method == "POST":
        # Create new adapter instance
        data = request.data

        # Get organization from UserContext
        organization = UserContext.get_organization()
        if not organization:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Map frontend type to adapter type enum value
        type_mapping = {
            "LLM": "LLM",
            "LLMWhisperer": "X2TEXT",
            "Embedding": "EMBEDDING",
            "VectorDB": "VECTOR_DB",
        }
        adapter_type = type_mapping.get(data.get("type", "LLM"), "LLM")

        # Build adapter metadata
        adapter_metadata = {
            "model": data.get("model", ""),
        }

        # Add API key and base URL if provided
        if data.get("api_key"):
            adapter_metadata["api_key"] = data["api_key"]
        if data.get("api_base"):
            adapter_metadata["api_base"] = data["api_base"]

        # Create adapter instance with organization
        adapter = AdapterInstance.objects.create(
            adapter_name=data.get("name"),
            adapter_id=data.get("provider", ""),
            adapter_type=adapter_type,
            adapter_metadata=adapter_metadata,
            description=data.get("description", ""),
            organization=organization,
            created_by=request.user,
            modified_by=request.user,
        )

        # Encrypt the metadata
        adapter.create_adapter()

        logger.info(f"Created adapter {adapter.id} for organization {organization.organization_id}")

        return Response({
            "id": str(adapter.id),
            "name": adapter.adapter_name,
            "type": data.get("type", "LLM"),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "description": data.get("description", ""),
        }, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsOrganizationMember])
def connector_detail(request: Request, connector_id: str):
    """Get, update, or delete a specific connector.

    GET: Retrieve connector details.
    PATCH/PUT: Update connector.
    DELETE: Delete connector.
    """
    from adapter_processor_v2.models import AdapterInstance

    organization = UserContext.get_organization()
    if not organization:
        return Response({"error": "Organization not found"}, status=status.HTTP_400_BAD_REQUEST)

    # Get the adapter instance
    try:
        adapter = AdapterInstance.objects.get(
            id=connector_id,
            organization=organization
        )
    except AdapterInstance.DoesNotExist:
        return Response({"error": "Connector not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response({
            "id": str(adapter.id),
            "name": adapter.adapter_name,
            "type": adapter.adapter_type if adapter.adapter_type else "LLM",
            "provider": adapter.adapter_id or "",
            "model": adapter.adapter_metadata.get("model", "") if adapter.adapter_metadata else "",
            "description": adapter.description or "",
        })

    elif request.method in ["PATCH", "PUT"]:
        # Update adapter
        data = request.data

        if "name" in data:
            adapter.adapter_name = data["name"]

        if "type" in data:
            # Map frontend type to adapter type enum value
            type_mapping = {
                "LLM": "LLM",
                "LLMWhisperer": "X2TEXT",
                "Embedding": "EMBEDDING",
                "VectorDB": "VECTOR_DB",
            }
            adapter.adapter_type = type_mapping.get(data["type"], "LLM")

        if "provider" in data:
            adapter.adapter_id = data["provider"]

        if "description" in data:
            adapter.description = data["description"]

        # Update metadata
        adapter_metadata = adapter.adapter_metadata or {}
        if "model" in data:
            adapter_metadata["model"] = data["model"]
        if "api_key" in data:
            adapter_metadata["api_key"] = data["api_key"]
        if "api_base" in data:
            adapter_metadata["api_base"] = data["api_base"]

        adapter.adapter_metadata = adapter_metadata
        adapter.modified_by = request.user
        adapter.save()

        # Re-encrypt metadata if changed
        if "api_key" in data or "api_base" in data or "model" in data:
            adapter.create_adapter()

        return Response({
            "id": str(adapter.id),
            "name": adapter.adapter_name,
            "type": data.get("type", adapter.adapter_type),
            "provider": adapter.adapter_id or "",
            "model": adapter_metadata.get("model", ""),
            "description": adapter.description or "",
        })

    elif request.method == "DELETE":
        adapter.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
