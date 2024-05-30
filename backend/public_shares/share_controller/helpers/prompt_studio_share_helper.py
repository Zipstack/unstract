import logging
from typing import Any

from django_tenants.utils import tenant_context
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.serializers import CustomToolSerializer
from public_shares.share_controller.exceptions import ShareControllerException
from public_shares.share_manager.models import ShareManager

logger = logging.getLogger(__name__)


class PromptShareHelper:

    @staticmethod
    def get_custom_tool_metadata(share_id: str) -> Any:
        try:
            share_manager = ShareManager.objects.get(share_id=share_id)
        except Exception as e:
            # TO DO : Handle exceptions
            logger.error(f"Error occured {e}")
            raise ShareControllerException(
                "Public sharing for this project is "
                "either removed or permission is revoked"
            )
        with tenant_context(share_manager.organization_id):
            tool: CustomTool = CustomTool.objects.get(share_id=share_id)
            serializer = CustomToolSerializer(tool).data
            return serializer
