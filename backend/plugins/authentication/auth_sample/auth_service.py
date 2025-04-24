import logging
import uuid
from abc import ABC
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response

from .auth_helper import AuthHelper
from .dto import AuthOrganization, ResetUserPasswordDto, TokenData, User, UserInfo
from .enums import Region
from .exceptions import MethodNotImplemented

Logger = logging.getLogger(__name__)


class AuthService(ABC):
    def __init__(self) -> None:
        self.authHelper: AuthHelper = AuthHelper()

    def user_login(self, request: Request, region: Region) -> Any:
        raise MethodNotImplemented()

    def user_signup(self, request: Request, region: Region) -> Any:
        raise MethodNotImplemented()

    def get_authorize_token(self, request: Request) -> TokenData:
        return self.authHelper.get_authorize_token(request)

    def user_organizations(
        self, user: User, token: dict[str, Any] | None = None
    ) -> list[AuthOrganization]:
        raise MethodNotImplemented()

    def get_user_info(
        self, user: User, token: dict[str, Any] | None = None
    ) -> UserInfo | None:
        return UserInfo(
            id=user.id,
            name=user.username,
            display_name=user.username,
            email=user.email,
        )

    def get_organization_info(self, org_id: str) -> Any:
        return None

    def make_organization_and_add_member(
        self,
        user_id: str,
        user_name: str,
        organization_name: str | None = None,
        display_name: str | None = None,
    ) -> AuthOrganization | None:
        raise MethodNotImplemented()

    def make_user_organization_name(self) -> str:
        return str(uuid.uuid4())

    def make_user_organization_display_name(self, user_name: str) -> str:
        name = f"{user_name}'s" if user_name else "Your"
        return f"{name} organization"

    def user_logout(self, request: Request) -> Response:
        return self.authHelper.auth_logout(request)

    def get_user_id_from_token(self, token: dict[str, Any]) -> Response:
        return token["userinfo"]["sub"]

    def get_organization_members_by_org_id(self, organization_id: str) -> Response:
        raise MethodNotImplemented()

    def reset_user_password(self, user: User) -> ResetUserPasswordDto:
        raise MethodNotImplemented()
