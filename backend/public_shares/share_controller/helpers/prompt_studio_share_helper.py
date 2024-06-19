import logging

from account.models import Organization
from django_tenants.utils import tenant_context
from prompt_studio.prompt_studio_core.models import CustomTool
from public_shares.share_controller.exceptions import ShareControllerException
from public_shares.share_manager.models import ShareManager

logger = logging.getLogger(__name__)


class PromptShareHelper:

    @staticmethod
    def get_share_manager_instance(share_id: str) -> ShareManager:
        try:
            share_manager: ShareManager = ShareManager.objects.get(share_id=share_id)
        except Exception as e:
            # TO DO : Handle exceptions
            logger.error(f"Error occured {e}")
            raise ShareControllerException(
                "Public sharing for this project is "
                "either removed or permission is revoked"
            )

        return share_manager

    @staticmethod
    def get_tool_from_share_id(share_id: str, org_id: Organization) -> str:
        with tenant_context(org_id):
            # TO DO : Handle exceptions
            tool: CustomTool = CustomTool.objects.get(share_id=share_id)
            tool_id: str = tool.tool_id
            return tool_id
