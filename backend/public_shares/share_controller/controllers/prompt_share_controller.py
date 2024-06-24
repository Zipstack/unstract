import logging
from typing import Any

from django_tenants.utils import tenant_context
from file_management.file_management_helper import FileManagerHelper
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_profile_manager.serializers import ProfileManagerSerializer
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.constants import FileViewTypes
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_core.serializers import CustomToolSerializer
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_document_manager.serializers import (
    PromptStudioDocumentManagerSerializer,
)
from prompt_studio.prompt_studio_output_manager.models import PromptStudioOutputManager
from prompt_studio.prompt_studio_output_manager.serializers import PromptStudioOutputSerializer
from public_shares.share_controller.exceptions import ShareControllerException
from public_shares.share_controller.helpers.prompt_studio_share_helper import (
    PromptShareHelper,
)
from public_shares.share_manager.models import ShareManager
from unstract.connectors.filesystems.local_storage.local_storage import LocalStorageFS

logger = logging.getLogger(__name__)


class PromptShareController:
    @staticmethod
    def get_document_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )  # Handle exception for tool not shared
        tool = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            try:
                document_manager: DocumentManager = DocumentManager.objects.filter(
                    tool_id=tool.tool_id
                )
            except DocumentManager.DoesNotExist as does_not_exist:
                logger.error(f"Document manager does not exisit:{does_not_exist}")
                raise ShareControllerException(
                    "Document cannot be loaded. It is either missing or moved."
                )
            serializer = PromptStudioDocumentManagerSerializer(
                document_manager, many=True
            ).data
            return serializer

    @staticmethod
    def get_custom_tool_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )
        with tenant_context(share_manager.organization_id):
            tool: CustomTool = CustomTool.objects.get(share_id=share_id)
            serializer = CustomToolSerializer(tool).data
            return serializer

    @staticmethod
    def get_profile_manager_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )
        tool = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            profile_manager_instances = ProfileManager.objects.filter(
                prompt_studio_tool=tool.tool_id
            )

            serialized_instances = ProfileManagerSerializer(
                profile_manager_instances, many=True
            ).data
            return serialized_instances

    @staticmethod
    def get_prompt_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )
        tool = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            prompt_instances: list[ToolStudioPrompt] = (
                PromptStudioHelper.fetch_prompt_from_tool(tool_id=tool.tool_id)
            )
            serialized_instances = ProfileManagerSerializer(
                prompt_instances, many=True
            ).data
            return serialized_instances
        
    @staticmethod
    def get_prompt_output_metadata(share_id:str, prompt_id:str, document_manager:str, profile_manager:str, is_single_pass:bool) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )  # Handle exception for tool not shared
        tool = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            output_metadata:PromptStudioOutputManager=PromptStudioOutputManager.objects.filter(tool_id=tool.tool_id,
                                                     prompt_id=prompt_id,
                                                     document_manager=document_manager,
                                                     profile_manager=profile_manager,
                                                     is_single_pass_extract=is_single_pass)
             
            serializer = PromptStudioOutputSerializer(output_metadata).data
            return serializer

    @staticmethod
    def get_prompt_studio_file_contents(share_id:str, document_id:str, view_type:str)->Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )
        tool_id = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            document: DocumentManager = DocumentManager.objects.get(pk=document_id)
            file_name: str = document.document_name
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
            org_id=str(share_manager.organization_id.organization_id),
            is_create=True,
            user_id=tool_id.created_by.user_id,
            tool_id=str(tool_id.tool_id),
        )
            file_system = LocalStorageFS(settings={"path": file_path})
            if not file_path.endswith("/"):
                file_path += "/"
            file_path += file_name
            contents = FileManagerHelper.fetch_file_contents(file_system, file_path)
            return contents
