from typing import Optional

from django.http import HttpRequest
from tenant_account.models import OrganizationMember
from utils.constants import FeatureFlag

from unstract.flags.feature_flag import check_feature_flag_status


class UserSessionUtils:
    @staticmethod
    def get_organization_id(request: HttpRequest) -> Optional[str]:
        session_org_id = request.session.get("organization")
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            requested_org_id = request.organization_id
            if requested_org_id and (session_org_id != requested_org_id):
                return None
        return session_org_id

    @staticmethod
    def set_organization_id(request: HttpRequest, organization_id: str) -> None:
        request.session["organization"] = organization_id

    @staticmethod
    def get_user_id(request: HttpRequest) -> Optional[str]:
        return request.session.get("user_id")

    @staticmethod
    def get_session_id(request: HttpRequest) -> Optional[str]:
        return request.session.session_key

    @staticmethod
    def set_organization_member_role(
        request: HttpRequest, member: OrganizationMember
    ) -> None:
        request.session["role"] = member.role

    @staticmethod
    def get_organization_member_role(request: HttpRequest) -> Optional[str]:
        return request.session.get("role")
