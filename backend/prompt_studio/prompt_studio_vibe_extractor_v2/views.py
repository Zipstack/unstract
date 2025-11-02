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
    VibeExtractorGenerateExtractionFieldsSerializer,
    VibeExtractorGenerateMetadataSerializer,
    VibeExtractorGeneratePagePromptsSerializer,
    VibeExtractorGenerateScalarPromptsSerializer,
    VibeExtractorGenerateSerializer,
    VibeExtractorGenerateTablePromptsSerializer,
    VibeExtractorGuessDocumentTypeSerializer,
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
    def generate_metadata(self, request: Request, pk=None) -> Response:
        """Generate only metadata for a project.

        Args:
            request: HTTP request
            pk: Project ID

        Returns:
            Response with generated metadata
        """
        serializer = VibeExtractorGenerateMetadataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()

            # Start generation in background
            import threading

            def run_generation():
                """Run metadata generation in background thread."""
                try:
                    GeneratorService.generate_metadata_only(project)
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Metadata generation started",
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

    @action(detail=True, methods=["post"])
    def generate_extraction_fields(self, request: Request, pk=None) -> Response:
        """Generate extraction fields for a project.

        Args:
            request: HTTP request with metadata
            pk: Project ID

        Returns:
            Response with generated extraction fields
        """
        serializer = VibeExtractorGenerateExtractionFieldsSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()
            metadata = serializer.validated_data["metadata"]

            # Start generation in background
            import threading

            def run_generation():
                """Run extraction fields generation in background thread."""
                try:
                    GeneratorService.generate_extraction_fields_only(
                        project, metadata
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Extraction fields generation started",
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

    @action(detail=True, methods=["post"])
    def generate_page_prompts(self, request: Request, pk=None) -> Response:
        """Generate page extraction prompts for a project.

        Args:
            request: HTTP request with metadata
            pk: Project ID

        Returns:
            Response with generated prompts
        """
        serializer = VibeExtractorGeneratePagePromptsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()
            metadata = serializer.validated_data["metadata"]

            # Start generation in background
            import threading

            def run_generation():
                """Run page prompts generation in background thread."""
                try:
                    GeneratorService.generate_page_extraction_prompts(
                        project, metadata
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Page prompts generation started",
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

    @action(detail=True, methods=["post"])
    def generate_scalar_prompts(self, request: Request, pk=None) -> Response:
        """Generate scalar extraction prompts for a project.

        Args:
            request: HTTP request with metadata and extraction_yaml
            pk: Project ID

        Returns:
            Response with generated prompts
        """
        serializer = VibeExtractorGenerateScalarPromptsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()
            metadata = serializer.validated_data["metadata"]
            extraction_yaml = serializer.validated_data["extraction_yaml"]

            # Start generation in background
            import threading

            def run_generation():
                """Run scalar prompts generation in background thread."""
                try:
                    GeneratorService.generate_scalar_extraction_prompts(
                        project, metadata, extraction_yaml
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Scalar prompts generation started",
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

    @action(detail=True, methods=["post"])
    def generate_table_prompts(self, request: Request, pk=None) -> Response:
        """Generate table extraction prompts for a project.

        Args:
            request: HTTP request with metadata and extraction_yaml
            pk: Project ID

        Returns:
            Response with generated prompts
        """
        serializer = VibeExtractorGenerateTablePromptsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            project = self.get_object()
            metadata = serializer.validated_data["metadata"]
            extraction_yaml = serializer.validated_data["extraction_yaml"]

            # Start generation in background
            import threading

            def run_generation():
                """Run table prompts generation in background thread."""
                try:
                    GeneratorService.generate_table_extraction_prompts(
                        project, metadata, extraction_yaml
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Background generation failed: {e}", exc_info=True)

            thread = threading.Thread(target=run_generation)
            thread.daemon = True
            thread.start()

            return Response(
                {
                    "message": "Table prompts generation started",
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

    @action(detail=False, methods=["post"])
    def guess_document_type(self, request: Request) -> Response:
        """Guess document type from file content.

        Args:
            request: HTTP request with file_name and tool_id

        Returns:
            Response with guessed document type
        """
        serializer = VibeExtractorGuessDocumentTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            file_name = serializer.validated_data["file_name"]
            tool_id = serializer.validated_data["tool_id"]

            # Call the helper to guess document type
            result = VibeExtractorHelper.guess_document_type_from_file(
                file_name=file_name,
                tool_id=str(tool_id),
                org_id=request.user.organization_id,
                user_id=request.user.user_id,
            )

            if result.get("status") == "error":
                return Response(
                    {
                        "error": result.get("error"),
                        "raw_response": result.get("raw_response"),
                        "attempted_json": result.get("attempted_json"),
                        "partial_response": result.get("partial_response"),
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            return Response(
                {
                    "document_type": result.get("document_type"),
                    "confidence": result.get("confidence"),
                    "primary_indicators": result.get("primary_indicators", []),
                    "document_category": result.get("document_category"),
                    "alternative_types": result.get("alternative_types", []),
                    "reasoning": result.get("reasoning"),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Failed to guess document type: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
