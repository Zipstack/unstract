from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.permission import PromptAcesssToUser
from prompt_studio.prompt_studio_vibe_extractor_v2.constants import (
    VibeExtractorKeys,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.exceptions import (
    FileReadError,
    GenerationError,
    InvalidDocumentTypeError,
    ProjectNotFoundError,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.models import (
    VibeExtractorProject,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.serializers import (
    VibeExtractorFileReadSerializer,
    VibeExtractorGenerateSerializer,
    VibeExtractorProjectCreateSerializer,
    VibeExtractorProjectSerializer,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.services.generator_service import (
    GeneratorService,
)
from prompt_studio.prompt_studio_vibe_extractor_v2.vibe_extractor_helper import (
    VibeExtractorHelper,
)


class VibeExtractorProjectView(viewsets.ModelViewSet):
    """Viewset to handle Vibe Extractor project CRUD operations.

    Provides endpoints for:
    - Creating new extraction projects
    - Listing projects
    - Retrieving project details
    - Updating project settings
    - Deleting projects
    - Triggering generation
    - Reading generated files
    """

    versioning_class = URLPathVersioning
    serializer_class = VibeExtractorProjectSerializer
    permission_classes: list[type[PromptAcesssToUser]] = [PromptAcesssToUser]

    def get_queryset(self) -> QuerySet:
        """Get queryset filtered by tool_id if provided."""
        filter_args = FilterHelper.build_filter_args(
            self.request,
            VibeExtractorKeys.TOOL_ID,
        )
        if filter_args:
            queryset = VibeExtractorProject.objects.filter(**filter_args)
        else:
            queryset = VibeExtractorProject.objects.all()
        return queryset

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Create a new Vibe Extractor project.

        Args:
            request: HTTP request with document_type and optional tool_id

        Returns:
            Response with created project data
        """
        serializer = VibeExtractorProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Validate and normalize document type
            document_type = VibeExtractorHelper.validate_document_type(
                serializer.validated_data["document_type"]
            )

            # Create project
            project = VibeExtractorProject.objects.create(
                document_type=document_type,
                tool_id_id=serializer.validated_data.get("tool_id"),
                created_by=request.user,
                modified_by=request.user,
            )

            # Create output directory
            output_path = VibeExtractorHelper.ensure_output_directory(project)
            project.generation_output_path = str(output_path)
            project.save(update_fields=["generation_output_path"])

            response_serializer = VibeExtractorProjectSerializer(project)
            return Response(
                response_serializer.data, status=status.HTTP_201_CREATED
            )

        except InvalidDocumentTypeError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to create project: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def generate(self, request: Request, pk=None) -> Response:
        """Trigger generation for a project.

        This endpoint will call the prompt service to generate
        all the metadata, extraction fields, and prompts.

        Args:
            request: HTTP request with optional regenerate flag
            pk: Project ID

        Returns:
            Response with generation status
        """
        serializer = VibeExtractorGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()

            # Check if already generating
            if project.status in [
                VibeExtractorProject.Status.GENERATING_METADATA,
                VibeExtractorProject.Status.GENERATING_FIELDS,
                VibeExtractorProject.Status.GENERATING_PROMPTS,
            ]:
                return Response(
                    {"error": "Generation already in progress"},
                    status=status.HTTP_409_CONFLICT,
                )

            # Update status to generating
            project.status = VibeExtractorProject.Status.GENERATING_METADATA
            project.save(update_fields=["status", "modified_at"])

            # Start generation in background
            # Note: In production, consider using Celery or similar for background tasks
            import threading

            def run_generation():
                """Run generation in background thread."""
                try:
                    GeneratorService.generate_all(project)
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Generation started",
                    "project_id": str(project.project_id),
                    "status": project.status,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except VibeExtractorProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def read_file(self, request: Request, pk=None) -> Response:
        """Read a generated file for a project.

        Args:
            request: HTTP request with file_type parameter
            pk: Project ID

        Returns:
            Response with file content
        """
        file_type = request.query_params.get("file_type")
        if not file_type:
            return Response(
                {"error": "file_type parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VibeExtractorFileReadSerializer(
            data={"file_type": file_type}
        )
        if not serializer.is_valid():
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = self.get_object()
            content = VibeExtractorHelper.read_generated_file(
                project, file_type
            )

            return Response(
                {
                    "file_type": file_type,
                    "content": content,
                    "project_id": str(project.project_id),
                },
                status=status.HTTP_200_OK,
            )

        except VibeExtractorProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except FileReadError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to read file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def list_files(self, request: Request, pk=None) -> Response:
        """List all generated files for a project.

        Args:
            request: HTTP request
            pk: Project ID

        Returns:
            Response with list of available files
        """
        try:
            project = self.get_object()
            output_path = VibeExtractorHelper.get_project_output_path(project)

            files = []
            file_types = [
                "metadata",
                "extraction",
                "page_extraction_system",
                "page_extraction_user",
                "scalars_extraction_system",
                "scalars_extraction_user",
                "tables_extraction_system",
                "tables_extraction_user",
            ]

            for file_type in file_types:
                try:
                    VibeExtractorHelper.read_generated_file(project, file_type)
                    files.append(
                        {"file_type": file_type, "exists": True}
                    )
                except FileReadError:
                    files.append(
                        {"file_type": file_type, "exists": False}
                    )

            return Response(
                {
                    "project_id": str(project.project_id),
                    "files": files,
                },
                status=status.HTTP_200_OK,
            )

        except VibeExtractorProject.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to list files: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
