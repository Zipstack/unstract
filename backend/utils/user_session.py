from typing import Optional

from django.http import HttpRequest
from tenant_account.models import OrganizationMember as OrganizationMember

class UserSessionUtils:
    @staticmethod
    def get_organization_id(request: HttpRequest) -> Optional[str]:
        return request.session.get("organization")

    @staticmethod
    def set_organization_id(request: HttpRequest, organization_id: str) -> None:
        request.session["organization"] = organization_id

    @staticmethod
    def get_user_id(request: HttpRequest) -> Optional[str]:
        return request.session.get("user_id")

    @staticmethod
    def set_organization_member_role(request: HttpRequest, member: OrganizationMember) -> None:
        request.session["role"] = member.role

    @staticmethod
    def get_organization_member_role(request: HttpRequest) -> Optional[str]:
        return request.session.get("role")