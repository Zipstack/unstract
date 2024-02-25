import logging
import uuid
from typing import Any, Optional

from account.authentication_helper import AuthenticationHelper
from account.cache_service import CacheService
from account.constants import Common, DefaultOrg
from account.custom_exceptions import Forbidden, MethodNotImplemented
from account.dto import (
    CallbackData,
    MemberData,
    MemberInvitation,
    OrganizationData,
    ResetUserPasswordDto,
    UserInfo,
    UserRoleData,
    UserSessionInfo,
)
from account.enums import UserRole
from account.models import Organization, User
from account.organization import OrganizationService
from django.http import HttpRequest
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account.models import OrganizationMember as OrganizationMember

Logger = logging.getLogger(__name__)


class AuthenticationService:
    def __init__(self) -> None:
        self.authentication_helper = AuthenticationHelper()
        self.default_user: User = self.get_user()
        self.default_organization: Organization = self.user_organization()
        self.user_session_info = self.get_user_session_info()

    def get_current_organization(self) -> Organization:
        return self.default_organization

    def get_current_user(self) -> User:
        return self.default_user

    def get_current_user_session(self) -> UserSessionInfo:
        return self.user_session_info

    def user_login(self, request: HttpRequest) -> Any:
        raise MethodNotImplemented()

    def user_signup(self, request: HttpRequest) -> Any:
        raise MethodNotImplemented()

    def is_admin_by_role(self, role: str) -> bool:
        """Check the role with actual admin Role.

        Args:
            role (str): input string

        Returns:
            bool: _description_
        """
        try:
            return UserRole(role.lower()) == UserRole.ADMIN
        except ValueError:
            return False

    def get_callback_data(self, request: Request) -> CallbackData:
        return CallbackData(
            user_id=DefaultOrg.MOCK_USER_ID,
            email=DefaultOrg.MOCK_USER_EMAIL,
            token="",
        )

    def user_organization(self) -> Organization:
        return Organization(
            name=DefaultOrg.ORGANIZATION_NAME,
            display_name=DefaultOrg.ORGANIZATION_NAME,
            organization_id=DefaultOrg.ORGANIZATION_NAME,
            schema_name=DefaultOrg.ORGANIZATION_NAME,
        )

    def handle_invited_user_while_callback(
        self, request: Request, user: User
    ) -> MemberData:
        member_data: MemberData = MemberData(
            user_id=self.default_user.user_id,
            organization_id=self.default_organization.organization_id,
            role=[UserRole.ADMIN.value],
        )

        return member_data

    def handle_authorization_callback(
        self, user: User, data: CallbackData, redirect_url: str = ""
    ) -> Response:
        return Response()

    def add_to_organization(
        self,
        request: Request,
        user: User,
        data: Optional[dict[str, Any]] = None,
    ) -> MemberData:
        member_data: MemberData = MemberData(
            user_id=self.default_user.user_id,
            organization_id=self.default_organization.organization_id,
        )

        return member_data

    def remove_users_from_organization(
        self,
        admin: OrganizationMember,
        organization_id: str,
        user_ids: list[str],
    ) -> bool:
        raise MethodNotImplemented()

    def user_organizations(self, request: Request) -> list[OrganizationData]:
        organizationData: OrganizationData = OrganizationData(
            id=self.default_organization.organization_id,
            display_name=self.default_organization.display_name,
            name=self.default_organization.name,
        )
        return [organizationData]

    def get_organizations_by_user_id(self, id: str) -> list[OrganizationData]:
        organizationData: OrganizationData = OrganizationData(
            id=self.default_organization.organization_id,
            display_name=self.default_organization.display_name,
            name=self.default_organization.name,
        )
        return [organizationData]

    def get_organization_role_of_user(
        self, user_id: str, organization_id: str
    ) -> list[str]:
        return [UserRole.ADMIN.value]

    def is_organization_admin(self, member: OrganizationMember) -> bool:
        """Check if the organization member has administrative privileges.

        Args:
            member (OrganizationMember): The organization member to check.

        Returns:
            bool: True if the user has administrative privileges,
                False otherwise.
        """
        try:
            return UserRole(member.role) == UserRole.ADMIN
        except ValueError:
            return False

    def check_user_organization_association(self, user_email: str) -> None:
        """Check if the user is already associated with any organizations.

        Raises:
        - UserAlreadyAssociatedException:
            If the user is already associated with organizations.
        """
        return None

    def get_roles(self) -> list[UserRoleData]:
        return [
            UserRoleData(name=UserRole.ADMIN.value),
            UserRoleData(name=UserRole.USER.value),
        ]

    def get_invitations(self, organization_id: str) -> list[MemberInvitation]:
        raise MethodNotImplemented()

    def delete_invitation(
        self, organization_id: str, invitation_id: str
    ) -> bool:
        raise MethodNotImplemented()

    def add_organization_user_role(
        self,
        admin: User,
        organization_id: str,
        user_id: str,
        role_ids: list[str],
    ) -> list[str]:
        if admin.role == UserRole.ADMIN.value:
            return role_ids
        raise Forbidden

    def remove_organization_user_role(
        self,
        admin: User,
        organization_id: str,
        user_id: str,
        role_ids: list[str],
    ) -> list[str]:
        if admin.role == UserRole.ADMIN.value:
            return role_ids
        raise Forbidden

    def get_organization_by_org_id(self, id: str) -> OrganizationData:
        organizationData: OrganizationData = OrganizationData(
            id=DefaultOrg.ORGANIZATION_NAME,
            display_name=DefaultOrg.ORGANIZATION_NAME,
            name=DefaultOrg.ORGANIZATION_NAME,
        )
        return organizationData

    def get_user(self) -> User:
        user = CacheService.get_user_session_info(DefaultOrg.MOCK_USER_EMAIL)
        if not user:
            try:
                user = User.objects.get(email=DefaultOrg.MOCK_USER_EMAIL)
            except User.DoesNotExist:
                user = User(
                    username=DefaultOrg.MOCK_USER,
                    user_id=DefaultOrg.MOCK_USER_ID,
                    email=DefaultOrg.MOCK_USER_EMAIL,
                )
                user.save()
        if isinstance(user, User):
            id = user.id
            user_id = user.user_id
            email = user.email
        else:
            id = user[Common.ID]
            user_id = user[Common.USER_ID]
            email = user[Common.USER_EMAIL]

        current_org = Common.PUBLIC_SCHEMA_NAME

        user_session_info: UserSessionInfo = UserSessionInfo(
            id=id,
            user_id=user_id,
            email=email,
            current_org=current_org,
        )
        CacheService.set_user_session_info(user_session_info)
        user_info = User(id=id, user_id=user_id, username=email, email=email)
        return user_info

    def get_user_info(self, request: Request) -> Optional[UserInfo]:
        user: User = request.user
        if user:
            return UserInfo(
                id=user.id,
                user_id=user.user_id,
                name=user.username,
                display_name=user.username,
                email=user.email,
            )
        else:
            user = self.get_user()
            return UserInfo(
                id=user.id,
                user_id=user.user_id,
                name=user.username,
                display_name=user.username,
                email=user.email,
            )

    def get_user_session_info(self) -> UserSessionInfo:
        user_session_info_dict = CacheService.get_user_session_info(
            self.default_user.email
        )
        if not user_session_info_dict:
            user_session_info: UserSessionInfo = UserSessionInfo(
                id=self.default_user.id,
                user_id=self.default_user.user_id,
                email=self.default_user.email,
                current_org=self.default_organization.organization_id,
            )
            CacheService.set_user_session_info(user_session_info)
        else:
            user_session_info = UserSessionInfo.from_dict(
                user_session_info_dict
            )
        return user_session_info

    def get_organization_info(self, org_id: str) -> Optional[Organization]:
        return OrganizationService.get_organization_by_org_id(org_id=org_id)

    def make_organization_and_add_member(
        self,
        user_id: str,
        user_name: str,
        organization_name: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Optional[OrganizationData]:
        organization: OrganizationData = OrganizationData(
            id=str(uuid.uuid4()),
            display_name=DefaultOrg.MOCK_ORG,
            name=DefaultOrg.MOCK_ORG,
        )
        return organization

    def make_user_organization_name(self) -> str:
        return str(uuid.uuid4())

    def make_user_organization_display_name(self, user_name: str) -> str:
        name = f"{user_name}'s" if user_name else "Your"
        return f"{name} organization"

    def user_logout(self, request: HttpRequest) -> Response:
        raise MethodNotImplemented()

    def get_user_id_from_token(
        self, token: Optional[dict[str, Any]]
    ) -> Response:
        return DefaultOrg.MOCK_USER_ID

    def get_organization_members_by_org_id(
        self, organization_id: str
    ) -> list[MemberData]:
        users: list[OrganizationMember] = OrganizationMember.objects.all()
        return self.authentication_helper.list_of_members_from_user_model(users)

    def reset_user_password(self, user: User) -> ResetUserPasswordDto:
        raise MethodNotImplemented()

    def invite_user(
        self,
        admin: OrganizationMember,
        org_id: str,
        email: str,
        role: Optional[str] = None,
    ) -> bool:
        raise MethodNotImplemented()
