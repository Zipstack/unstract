import logging
import uuid
from typing import Any, Optional

from account_v2.authentication_helper import AuthenticationHelper
from account_v2.constants import DefaultOrg, ErrorMessage, UserLoginTemplate
from account_v2.custom_exceptions import Forbidden, MethodNotImplemented
from account_v2.dto import (
    CallbackData,
    MemberData,
    MemberInvitation,
    OrganizationData,
    ResetUserPasswordDto,
    UserInfo,
    UserRoleData,
)
from account_v2.enums import UserRole
from account_v2.models import Organization, User
from account_v2.organization import OrganizationService
from account_v2.serializer import LoginRequestSerializer
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.http import HttpRequest
from django.shortcuts import redirect, render
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account_v2.models import OrganizationMember as OrganizationMember
from tenant_account_v2.organization_member_service import OrganizationMemberService

Logger = logging.getLogger(__name__)


class AuthenticationService:
    def __init__(self) -> None:
        self.authentication_helper = AuthenticationHelper()
        self.default_organization: Organization = self.user_organization()

    def user_login(self, request: Request) -> Any:
        """Authenticate and log in a user.

        Args:
            request (Request): The HTTP request object.

        Returns:
            Any: The response object.

        Raises:
            ValueError: If there is an error in the login credentials.
        """
        if request.method == "GET":
            return self.render_login_page(request)
        try:
            validated_data = self.validate_login_credentials(request)
            username = validated_data.get("username")
            password = validated_data.get("password")
        except ValueError as e:
            return render(
                request,
                UserLoginTemplate.TEMPLATE,
                {UserLoginTemplate.ERROR_PLACE_HOLDER: str(e)},
            )
        if self.authenticate_and_login(request, username, password):
            return redirect(settings.WEB_APP_ORIGIN_URL)

        return self.render_login_page_with_error(request, ErrorMessage.USER_LOGIN_ERROR)

    def is_authenticated(self, request: HttpRequest) -> bool:
        """Check if the user is authenticated.

        Args:
            request (Request): The HTTP request object.

        Returns:
            bool: True if the user is authenticated, False otherwise.
        """
        return request.user.is_authenticated

    def authenticate_and_login(
        self, request: Request, username: str, password: str
    ) -> bool:
        """Authenticate and log in a user.

        Args:
            request (Request): The HTTP request object.
            username (str): The username of the user.
            password (str): The password of the user.

        Returns:
            bool: True if the user is successfully authenticated and logged in,
                False otherwise.
        """
        user = authenticate(request, username=username, password=password)
        if user:
            # To avoid conflicts with django superuser
            if user.is_superuser:
                return False
            login(request, user)
            return True
        # Attempt to initiate default user and authenticate again
        if self.set_default_user(username, password):
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                return True
        return False

    def render_login_page(self, request: Request) -> Any:
        return render(request, UserLoginTemplate.TEMPLATE)

    def render_login_page_with_error(self, request: Request, error_message: str) -> Any:
        return render(
            request,
            UserLoginTemplate.TEMPLATE,
            {UserLoginTemplate.ERROR_PLACE_HOLDER: error_message},
        )

    def validate_login_credentials(self, request: Request) -> Any:
        """Validate the login credentials.

        Args:
            request (Request): The HTTP request object.

        Returns:
            dict: The validated login credentials.

        Raises:
            ValueError: If the login credentials are invalid.
        """
        serializer = LoginRequestSerializer(data=request.POST)
        if not serializer.is_valid():
            error_messages = {
                field: errors[0] for field, errors in serializer.errors.items()
            }
            first_error_message = list(error_messages.values())[0]
            raise ValueError(first_error_message)
        return serializer.validated_data

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
            user_id=request.user.user_id,
            email=request.user.email,
            token="",
        )

    def user_organization(self) -> Organization:
        return Organization(
            name=DefaultOrg.ORGANIZATION_NAME,
            display_name=DefaultOrg.ORGANIZATION_NAME,
            organization_id=DefaultOrg.ORGANIZATION_NAME,
        )

    def handle_invited_user_while_callback(
        self, request: Request, user: User
    ) -> MemberData:
        member_data: MemberData = MemberData(
            user_id=user.user_id,
            organization_id=self.default_organization.organization_id,
            role=[UserRole.ADMIN.value],
        )

        return member_data

    def handle_authorization_callback(self, request: Request, backend: str) -> Response:
        raise MethodNotImplemented()

    def add_to_organization(
        self,
        request: Request,
        user: User,
        data: Optional[dict[str, Any]] = None,
    ) -> MemberData:
        member_data: MemberData = MemberData(
            user_id=user.user_id,
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

    def frictionless_onboarding(self, organization: Organization, user: User) -> None:
        raise MethodNotImplemented()

    def hubspot_signup_api(self, request: Request) -> None:
        raise MethodNotImplemented()

    def delete_invitation(self, organization_id: str, invitation_id: str) -> bool:
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

    def set_default_user(self, username: str, password: str) -> bool:
        """Set the default user for authentication.

        This method creates a default user with the provided username and
        password if the username and password match the default values defined
        in the 'DefaultOrg' class. The default user is saved in the database.

        Args:
            username (str): The username of the default user.
            password (str): The password of the default user.

        Returns:
            bool: True if the default user is successfully created and saved,
                False otherwise.
        """
        if (
            username != DefaultOrg.MOCK_USER
            or password != DefaultOrg.MOCK_USER_PASSWORD
        ):
            return False

        user, created = User.objects.get_or_create(username=DefaultOrg.MOCK_USER)
        if created:
            user.password = make_password(DefaultOrg.MOCK_USER_PASSWORD)
        else:
            user.user_id = DefaultOrg.MOCK_USER_ID
            user.email = DefaultOrg.MOCK_USER_EMAIL
            user.password = make_password(DefaultOrg.MOCK_USER_PASSWORD)
        user.save()
        return True

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
            return None

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
        """Log out the user.

        Args:
            request (HttpRequest): The HTTP request object.

        Returns:
            Response: The redirect response to the web app origin URL.
        """
        logout(request)
        return redirect(settings.WEB_APP_ORIGIN_URL)

    def get_organization_members_by_org_id(
        self, organization_id: str
    ) -> list[MemberData]:
        users: list[OrganizationMember] = OrganizationMemberService.get_members()
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
