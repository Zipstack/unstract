from typing import Any

from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from tenant_account_v2.models import OrganizationMember


class UserSessionUtils:
    @staticmethod
    def get_organization_id(request: HttpRequest) -> str | None:
        session_org_id = request.session.get("organization")
        requested_org_id = request.organization_id
        if requested_org_id and (session_org_id != requested_org_id):
            return None
        return session_org_id

    @staticmethod
    def set_organization_id(request: HttpRequest, organization_id: str) -> None:
        request.session["organization"] = organization_id

    @staticmethod
    def get_user_id(request: HttpRequest) -> str | None:
        return request.session.get("user_id")

    @staticmethod
    def set_organization_member_role(
        request: HttpRequest, member: OrganizationMember
    ) -> None:
        request.session["role"] = member.role

    @staticmethod
    def get_session_id(request: HttpRequest) -> str | None:
        return request.session.session_key

    @staticmethod
    def get_organization_member_role(request: HttpRequest) -> str | None:
        return request.session.get("role")

    @staticmethod
    def get_token_data(request: HttpRequest) -> Any | None:
        return request.session.get("token_data")

    @classmethod
    def is_authorized_path(cls, request: HttpRequest) -> bool:
        """Checks if the requested path is authorized based on the organization
        ID of user.

        Args:
            request (HttpRequest): The HTTP request containing session data,
            including the organization ID.

        Returns:
            bool: `True` if the path is authorized; `False` otherwise.
        """
        requested_organization_uid = connection.tenant.organization_id

        # Always authorize if the organization is public
        if requested_organization_uid == settings.PUBLIC_ORG_ID:
            return True

        # Get the session organization UID
        session_organization_uid = cls.get_organization_id(request=request)

        return requested_organization_uid == session_organization_uid
