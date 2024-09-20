import logging
import uuid
from typing import Any, Optional

from account_v2.custom_exceptions import DuplicateData
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpRequest
from file_management.exceptions import FileNotFound
from file_management.file_management_helper import FileManagerHelper
from permissions.permission import IsOwner, IsOwnerOrSharedUser
from prompt_studio.processor_loader import get_plugin_class_by_name, load_plugins
from prompt_studio.prompt_profile_manager_v2.constants import (
    ProfileManagerErrors,
    ProfileManagerKeys,
)
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_profile_manager_v2.serializers import ProfileManagerSerializer
from prompt_studio.prompt_studio_core_v2.constants import (
    FileViewTypes,
    ToolStudioErrors,
    ToolStudioKeys,
    ToolStudioPromptKeys,
)
from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
    DocumentIndexingService,
)
from prompt_studio.prompt_studio_core_v2.exceptions import (
    IndexingAPIError,
    MaxProfilesReachedError,
    ToolDeleteError,
)
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_document_manager_v2.prompt_studio_document_helper import (  # noqa: E501
    PromptStudioDocumentHelper,
)
from prompt_studio.prompt_studio_index_manager_v2.models import IndexManager
from prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper import (
    PromptStudioRegistryHelper,
)
from prompt_studio.prompt_studio_registry_v2.serializers import (
    ExportToolRequestSerializer,
    PromptStudioRegistryInfoSerializer,
)
from prompt_studio.prompt_studio_v2.constants import ToolStudioPromptErrors
from prompt_studio.prompt_studio_v2.serializers import ToolStudioPromptSerializer
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance.models import ToolInstance
from unstract.sdk.utils.common_utils import CommonUtils
from utils.user_session import UserSessionUtils

from unstract.connectors.filesystems.local_storage.local_storage import LocalStorageFS

from .models import CustomTool
from .serializers import (
    CustomToolSerializer,
    FileInfoIdeSerializer,
    FileUploadIdeSerializer,
    PromptStudioIndexSerializer,
    SharedUserListSerializer,
)

logger = logging.getLogger(__name__)


class PromptStudioCoreView(viewsets.ModelViewSet):
    """Viewset to handle all Custom tool related operations."""

    versioning_class = URLPathVersioning

    serializer_class = CustomToolSerializer

    processor_plugins = load_plugins()

    def get_permissions(self) -> list[Any]:
        if self.action == "destroy":
            return [IsOwner()]

        return [IsOwnerOrSharedUser()]

    def get_queryset(self) -> Optional[QuerySet]:
        return CustomTool.objects.for_user(self.request.user)

    def create(self, request: HttpRequest) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolStudioErrors.TOOL_NAME_EXISTS}, \
                    {ToolStudioErrors.DUPLICATE_API}"
            )
        PromptStudioHelper.create_default_profile_manager(
            request.user, serializer.data["tool_id"]
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: CustomTool) -> None:
        organization_id = UserSessionUtils.get_organization_id(self.request)
        instance.delete(organization_id)

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        instance: CustomTool = self.get_object()
        # Checks if tool is exported
        if hasattr(instance, "prompt_studio_registry"):
            exported_tool_instances_in_use = ToolInstance.objects.filter(
                tool_id__exact=instance.prompt_studio_registry.pk
            )
            dependent_wfs = set()
            for tool_instance in exported_tool_instances_in_use:
                dependent_wfs.add(tool_instance.workflow_id)
            if len(dependent_wfs) > 0:
                logger.info(
                    f"Cannot destroy custom tool {instance.tool_id},"
                    f" depended by workflows {dependent_wfs}"
                )
                raise ToolDeleteError(
                    "Failed to delete tool, its used in other workflows. "
                    "Delete its usages first"
                )
        return super().destroy(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        summarize_llm_profile_id = request.data.get(
            ToolStudioKeys.SUMMARIZE_LLM_PROFILE, None
        )
        if summarize_llm_profile_id:
            prompt_tool = self.get_object()

            ProfileManager.objects.filter(prompt_studio_tool=prompt_tool).update(
                is_summarize_llm=False
            )
            profile_manager = ProfileManager.objects.get(pk=summarize_llm_profile_id)
            profile_manager.is_summarize_llm = True
            profile_manager.save()

        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def get_select_choices(self, request: HttpRequest) -> Response:
        """Method to return all static dropdown field values.

        The field values are retrieved from `./static/select_choices.json`.

        Returns:
            Response: Reponse of dropdown dict
        """
        try:
            select_choices: dict[str, Any] = PromptStudioHelper.get_select_fields()
            return Response(select_choices, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error occured while fetching select fields {e}")
            return Response(select_choices, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def list_profiles(self, request: HttpRequest, pk: Any = None) -> Response:
        prompt_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        profile_manager_instances = ProfileManager.objects.filter(
            prompt_studio_tool=prompt_tool
        )

        serialized_instances = ProfileManagerSerializer(
            profile_manager_instances, many=True
        ).data

        return Response(serialized_instances)

    @action(detail=True, methods=["patch"])
    def make_profile_default(self, request: HttpRequest, pk: Any = None) -> Response:
        prompt_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        ProfileManager.objects.filter(prompt_studio_tool=prompt_tool).update(
            is_default=False
        )

        profile_manager = ProfileManager.objects.get(pk=request.data["default_profile"])
        profile_manager.is_default = True
        profile_manager.save()

        return Response(
            status=status.HTTP_200_OK,
            data={"default_profile": profile_manager.profile_id},
        )

    @action(detail=True, methods=["post"])
    def index_document(self, request: HttpRequest, pk: Any = None) -> Response:
        """API Entry point method to index input file.

        Args:
            request (HttpRequest)

        Raises:
            IndexingError
            ValidationError

        Returns:
            Response
        """
        tool = self.get_object()
        serializer = PromptStudioIndexSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get(
            ToolStudioPromptKeys.DOCUMENT_ID
        )
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        file_name: str = document.document_name
        text_processor = get_plugin_class_by_name(
            name="text_processor",
            plugins=self.processor_plugins,
        )
        # Generate a run_id
        run_id = CommonUtils.generate_uuid()
        unique_id = PromptStudioHelper.index_document(
            tool_id=str(tool.tool_id),
            file_name=file_name,
            org_id=UserSessionUtils.get_organization_id(request),
            user_id=tool.created_by.user_id,
            document_id=document_id,
            run_id=run_id,
            text_processor=text_processor,
        )

        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[ToolStudioPromptKeys.RUN_ID] = run_id
        cls = get_plugin_class_by_name(
            name="summarizer",
            plugins=self.processor_plugins,
        )
        if cls:
            cls.process(
                tool_id=str(tool.tool_id),
                file_name=file_name,
                org_id=UserSessionUtils.get_organization_id(request),
                user_id=tool.created_by.user_id,
                document_id=document_id,
                usage_kwargs=usage_kwargs.copy(),
            )

        if unique_id:
            return Response(
                {"message": "Document indexed successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            logger.error("Error occured while indexing. Unique ID is not valid.")
            raise IndexingAPIError()

    @action(detail=True, methods=["post"])
    def fetch_response(self, request: HttpRequest, pk: Any = None) -> Response:
        """API Entry point method to fetch response to prompt.

        Args:
            request (HttpRequest): _description_

        Raises:
            FilenameMissingError: _description_

        Returns:
            Response
        """
        custom_tool = self.get_object()
        tool_id: str = str(custom_tool.tool_id)
        document_id: str = request.data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        id: str = request.data.get(ToolStudioPromptKeys.ID)
        run_id: str = request.data.get(ToolStudioPromptKeys.RUN_ID)
        profile_manager: str = request.data.get(ToolStudioPromptKeys.PROFILE_MANAGER_ID)
        if not run_id:
            # Generate a run_id
            run_id = CommonUtils.generate_uuid()
        text_processor = get_plugin_class_by_name(
            name="text_processor",
            plugins=self.processor_plugins,
        )
        response: dict[str, Any] = PromptStudioHelper.prompt_responder(
            id=id,
            tool_id=tool_id,
            org_id=UserSessionUtils.get_organization_id(request),
            user_id=custom_tool.created_by.user_id,
            document_id=document_id,
            run_id=run_id,
            profile_manager_id=profile_manager,
            text_processor=text_processor,
        )
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def single_pass_extraction(self, request: HttpRequest, pk: uuid) -> Response:
        """API Entry point method to fetch response to prompt.

        Args:
            request (HttpRequest): _description_
            pk (Any): Primary key of the CustomTool

        Returns:
            Response
        """
        # TODO: Handle fetch_response and single_pass_
        # extraction using common function
        custom_tool = self.get_object()
        tool_id: str = str(custom_tool.tool_id)
        document_id: str = request.data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        run_id: str = request.data.get(ToolStudioPromptKeys.RUN_ID)
        if not run_id:
            # Generate a run_id
            run_id = CommonUtils.generate_uuid()
        text_processor = get_plugin_class_by_name(
            name="text_processor",
            plugins=self.processor_plugins,
        )
        response: dict[str, Any] = PromptStudioHelper.prompt_responder(
            tool_id=tool_id,
            org_id=UserSessionUtils.get_organization_id(request),
            user_id=custom_tool.created_by.user_id,
            document_id=document_id,
            run_id=run_id,
            text_processor=text_processor,
        )
        return Response(response, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:

        custom_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        serialized_instances = SharedUserListSerializer(custom_tool).data

        return Response(serialized_instances)

    @action(detail=True, methods=["post"])
    def create_prompt(self, request: HttpRequest, pk: Any = None) -> Response:
        context = super().get_serializer_context()
        serializer = ToolStudioPromptSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        try:
            # serializer.save()
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolStudioPromptErrors.PROMPT_NAME_EXISTS}, \
                    {ToolStudioPromptErrors.DUPLICATE_API}"
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def create_profile_manager(self, request: HttpRequest, pk: Any = None) -> Response:
        context = super().get_serializer_context()
        serializer = ProfileManagerSerializer(data=request.data, context=context)

        serializer.is_valid(raise_exception=True)
        # Check for the maximum number of profiles constraint
        prompt_studio_tool = serializer.validated_data[
            ProfileManagerKeys.PROMPT_STUDIO_TOOL
        ]
        profile_count = ProfileManager.objects.filter(
            prompt_studio_tool=prompt_studio_tool
        ).count()

        if profile_count >= ProfileManagerKeys.MAX_PROFILE_COUNT:
            raise MaxProfilesReachedError()
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ProfileManagerErrors.PROFILE_NAME_EXISTS}, \
                    {ProfileManagerErrors.DUPLICATE_API}"
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def fetch_contents_ide(self, request: HttpRequest, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serializer = FileInfoIdeSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get("document_id")
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        file_name: str = document.document_name
        view_type: str = serializer.validated_data.get("view_type")

        filename_without_extension = file_name.rsplit(".", 1)[0]
        if view_type == FileViewTypes.EXTRACT:
            file_name = (
                f"{FileViewTypes.EXTRACT.lower()}/" f"{filename_without_extension}.txt"
            )
        if view_type == FileViewTypes.SUMMARIZE:
            file_name = (
                f"{FileViewTypes.SUMMARIZE.lower()}/"
                f"{filename_without_extension}.txt"
            )

        file_path = file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            UserSessionUtils.get_organization_id(request),
            is_create=True,
            user_id=custom_tool.created_by.user_id,
            tool_id=str(custom_tool.tool_id),
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        if not file_path.endswith("/"):
            file_path += "/"
        file_path += file_name
        # Temporary Hack for frictionless onboarding as the user id will be empty
        try:
            contents = FileManagerHelper.fetch_file_contents(file_system, file_path)
        except FileNotFound:
            file_path = file_path = FileManagerHelper.handle_sub_directory_for_tenants(
                UserSessionUtils.get_organization_id(request),
                is_create=True,
                user_id="",
                tool_id=str(custom_tool.tool_id),
            )
            if not file_path.endswith("/"):
                file_path += "/"
                file_path += file_name
            contents = FileManagerHelper.fetch_file_contents(file_system, file_path)

        return Response({"data": contents}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def upload_for_ide(self, request: HttpRequest, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serializer = FileUploadIdeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_files: Any = serializer.validated_data.get("file")

        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            UserSessionUtils.get_organization_id(request),
            is_create=True,
            user_id=custom_tool.created_by.user_id,
            tool_id=str(custom_tool.tool_id),
        )
        file_system = LocalStorageFS(settings={"path": file_path})

        documents = []
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name

            # Create a record in the db for the file
            document = PromptStudioDocumentHelper.create(
                tool_id=str(custom_tool.tool_id), document_name=file_name
            )
            # Create a dictionary to store document data
            doc = {
                "document_id": document.document_id,
                "document_name": document.document_name,
                "tool": document.tool.tool_id,
            }
            # Store file
            logger.info(
                f"Uploading file: {file_name}" if file_name else "Uploading file"
            )
            FileManagerHelper.upload_file(
                file_system,
                file_path,
                uploaded_file,
                file_name,
            )
            documents.append(doc)
        return Response({"data": documents})

    @action(detail=True, methods=["delete"])
    def delete_for_ide(self, request: HttpRequest, pk: uuid) -> Response:
        custom_tool = self.get_object()
        serializer = FileInfoIdeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get(
            ToolStudioPromptKeys.DOCUMENT_ID
        )
        org_id = UserSessionUtils.get_organization_id(request)
        user_id = custom_tool.created_by.user_id
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        file_name: str = document.document_name
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            org_id=org_id,
            is_create=False,
            user_id=user_id,
            tool_id=str(custom_tool.tool_id),
        )
        path = file_path
        file_system = LocalStorageFS(settings={"path": path})
        try:
            # Delete indexed flags in redis
            index_managers = IndexManager.objects.filter(document_manager=document_id)
            for index_manager in index_managers:
                raw_index_id = index_manager.raw_index_id
                DocumentIndexingService.remove_document_indexing(
                    org_id=org_id, user_id=user_id, doc_id_key=raw_index_id
                )
            # Delete the document record
            document.delete()
            # Delete the files
            FileManagerHelper.delete_file(file_system, path, file_name)
            # Directories to delete the text files
            directories = ["extract/", "extract/metadata/", "summarize/"]
            FileManagerHelper.delete_related_files(
                file_system, path, file_name, directories
            )
            return Response(
                {"data": "File deleted succesfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error(f"Exception thrown from file deletion, error {exc}")
            return Response(
                {"data": "File deletion failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def export_tool(self, request: Request, pk: Any = None) -> Response:
        """API Endpoint for exporting required jsons for the custom tool."""
        custom_tool = self.get_object()
        serializer = ExportToolRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_shared_with_org: bool = serializer.validated_data.get("is_shared_with_org")
        user_ids = set(serializer.validated_data.get("user_id"))

        PromptStudioRegistryHelper.update_or_create_psr_tool(
            custom_tool=custom_tool,
            shared_with_org=is_shared_with_org,
            user_ids=user_ids,
        )
        return Response(
            {"message": "Custom tool exported sucessfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def export_tool_info(self, request: Request, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serialized_instances = None
        if hasattr(custom_tool, "prompt_studio_registry"):
            serialized_instances = PromptStudioRegistryInfoSerializer(
                custom_tool.prompt_studio_registry
            ).data

            return Response(serialized_instances)
        else:
            return Response(status=status.HTTP_204_NO_CONTENT)
