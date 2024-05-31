import logging
from typing import Any

from django_tenants.utils import tenant_context
from prompt_studio.prompt_studio_core.models import CustomTool
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
        )
        tool_id = PromptShareHelper.get_tool_from_share_id(
            share_id=share_id, org_id=share_manager.organization_id
        )
        with tenant_context(share_manager.organization_id):
            document_manager: DocumentManager = DocumentManager.objects.get(
                tool_id=tool_id
            )
            serializer = PromptStudioDocumentManagerSerializer(document_manager)
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
