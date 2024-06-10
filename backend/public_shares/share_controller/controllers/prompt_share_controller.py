import logging
from typing import Any

from django_tenants.utils import tenant_context
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_profile_manager.serializers import ProfileManagerSerializer
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_core.serializers import CustomToolSerializer
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_document_manager.serializers import (
    PromptStudioDocumentManagerSerializer,
)
from public_shares.share_controller.helpers.prompt_studio_share_helper import (
    PromptShareHelper,
)
from public_shares.share_manager.models import ShareManager

logger = logging.getLogger(__name__)


class PromptShareController:
    @staticmethod
    def get_document_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )  # Handle exception for tool not shared
        tool_id = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            try:
                document_manager: DocumentManager = DocumentManager.objects.filter(
                    tool_id=tool_id
                )
            except DocumentManager.DoesNotExist as does_not_exist:
                pass
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
        tool_id = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            profile_manager_instances = ProfileManager.objects.filter(
                prompt_studio_tool=tool_id
            )

            serialized_instances = ProfileManagerSerializer(
                profile_manager_instances, many=True
            ).data
            return serialized_instances

    @staticmethod
    def get_prompt_manager_metadata(share_id: str) -> Any:
        share_manager: ShareManager = PromptShareHelper.get_share_manager_instance(
            share_id
        )
        tool_id = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            prompt_instances: list[ToolStudioPrompt] = (
                PromptStudioHelper.fetch_prompt_from_tool(tool_id=tool_id)
            )
            serialized_instances = ProfileManagerSerializer(
                prompt_instances, many=True
            ).data
            return serialized_instances
