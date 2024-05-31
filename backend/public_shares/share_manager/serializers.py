import logging
from typing import Any, Optional

from account.organization import OrganizationService
from prompt_studio.prompt_studio_core.models import CustomTool
from public_shares.share_manager.constants import ShareManagerConstants as SMConstants
from rest_framework.request import Request
from utils.user_session import UserSessionUtils

from backend.serializers import AuditSerializer

from .exceptions import ShareManagerException
from .models import ShareManager

logger = logging.getLogger(__name__)


class ShareSerializer(AuditSerializer):
    class Meta:
        model = ShareManager
        fields = "__all__"

    def to_representation(self, instance: ShareManager) -> dict[str, Any]:
        representation: dict[str, str] = super().to_representation(instance)
        return representation

    def create(self, validated_data: dict[str, Any]) -> Any:
        request: Request = self.context["request"]
        share_type = request.query_params.get("share_type")
        org_id: Optional[str] = UserSessionUtils.get_organization_id(request)
        validated_data["organization_id"] = (
            OrganizationService.get_organization_by_org_id(org_id)
        )
        validated_data["share_type"] = share_type
        share: ShareManager = super().create(validated_data)
        id = request.query_params.get("id")
        if not id:
            raise ShareManagerException(
                "Unexpected server error. Please contact admin."
            )
        if share_type is SMConstants.ShareTypes.PROMPT_STUDIO:
            self.link_prompt_studio(share, id)
        return share

    def link_prompt_studio(self, share: ShareManager, tool_id: str) -> None:
        try:
            tool: CustomTool = CustomTool.objects.get(tool_id=tool_id)
        except Exception as e:
            # TO DO : Add better exception handling
            logger.error(f"Error occured : {e}")
            raise ShareManagerException("")
        if not tool.share_id:
            tool.share_id = share
            tool.save()
        else:
            raise ShareManagerException("Prompt sudio project already shared.")
