import logging
from typing import Any, Optional, Union
from urllib.parse import urlencode

from account.authentication_helper import AuthenticationHelper
from account.authentication_plugin_registry import AuthenticationPluginRegistry
from account.authentication_service import AuthenticationService
from account.constants import (
    AuthorizationErrorCode,
    Common,
    Cookie,
    ErrorMessage,
    OrganizationMemberModel,
)
from account.custom_exceptions import (
    DuplicateData,
    Forbidden,
    MethodNotImplemented,
    UserNotExistError,
)
from account.dto import (
    CallbackData,
    MemberInvitation,
    OrganizationData,
    UserInfo,
    UserInviteResponse,
    UserRoleData,
)
from account.exceptions import OrganizationNotExist
from account.models import Organization, User
from account.organization import OrganizationService
from account.serializer import (
    GetOrganizationsResponseSerializer,
    OrganizationSerializer,
    SetOrganizationsResponseSerializer,
)
from account.user import UserService
from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db.utils import IntegrityError
from django.middleware import csrf
from django.shortcuts import redirect
from django_tenants.utils import tenant_context
from psycopg2.errors import UndefinedTable
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account.models import OrganizationMember as OrganizationMember
from tenant_account.organization_member_service import OrganizationMemberService
from utils.cache_service import CacheService
from utils.local_context import StateStore

Logger = logging.getLogger(__name__)


class AuthenticationController:
    """Authentication Controller This controller class manages user
    authentication processes."""

    def __init__(self) -> None:
        """This method initializes the controller by selecting the appropriate
        authentication plugin based on availability."""
        self.authentication_helper = AuthenticationHelper()
        self.organization_member_service = OrganizationMemberService()
        if AuthenticationPluginRegistry.is_plugin_available():
            self.auth_service: AuthenticationService = (
                AuthenticationPluginRegistry.get_plugin()
            )
        else:
            self.auth_service = AuthenticationService()

    def user_login(
        self,
        request: Request,
    ) -> Any:
        return self.auth_service.user_login(request)

    def user_signup(self, request: Request) -> Any:
        return self.auth_service.user_signup(request)

    def authorization_callback(
        self, request: Request, backend: str = settings.DEFAULT_MODEL_BACKEND
    ) -> Any:
        """Handle authorization callback.

        This function processes the authorization callback from
        an external service.

        Args:
            request (Request): Request instance
            backend (str, optional): backend used to use login.
                Defaults: settings.DEFAULT_MODEL_BACKEND.

        Returns:
            Any: Redirect response
        """

        callback_data: CallbackData = self.auth_service.get_callback_data(
            request=request
        )
        user: User = self.get_or_create_user_by_email(request, callback_data)
        try:
            member = self.auth_service.handle_invited_user_while_callback(
                request=request, user=user
            )

        except Exception as ex:
            """Error code reference
            frontend/src/components/error/GenericError/GenericError.jsx."""
            if ex.code == AuthorizationErrorCode.IDM:  # type: ignore
                query_params = {"code": AuthorizationErrorCode.IDM}
                return redirect(
                    f"{settings.ERROR_URL}?{urlencode(query_params)}"
                )
            elif ex.code == AuthorizationErrorCode.UMM:  # type: ignore
                query_params = {"code": AuthorizationErrorCode.UMM}
                return redirect(
                    f"{settings.ERROR_URL}?{urlencode(query_params)}"
                )

            return redirect(f"{settings.ERROR_URL}")

        if member.organization_id and member.role and len(member.role) > 0:
            organization: Optional[Organization] = (
                OrganizationService.get_organization_by_org_id(
                    member.organization_id
                )
            )
            if organization:
                try:
                    self.create_tenant_user(
                        organization=organization, user=user
                    )
                except UndefinedTable:
                    pass

        response = self.auth_service.handle_authorization_callback(
            user=user,
            data=callback_data,
            redirect_url=request.GET.get("redirect_url"),
        )
        django_login(request, user, backend)

        return response

    def user_organizations(self, request: Request) -> Any:
        """List a user's organizations.

        Args:
            user (User): User instance
            z_code (str): _description_

        Returns:
            list[OrganizationData]: _description_
        """

        try:
            organizations = self.auth_service.user_organizations(request)
        except Exception as ex:
            #
            self.user_logout(request)
            if ex.code == AuthorizationErrorCode.USF:  # type: ignore
                response = Response(
                    status=status.HTTP_412_PRECONDITION_FAILED,
                    data={"domain": ex.data.get("domain")},  # type: ignore
                )
                return response
        user: User = request.user
        org_ids = {org.id for org in organizations}
        CacheService.set_user_organizations(user.user_id, list(org_ids))

        serialized_organizations = GetOrganizationsResponseSerializer(
            organizations, many=True
        ).data
        response = Response(
            status=status.HTTP_200_OK,
            data={
                "message": "success",
                "organizations": serialized_organizations,
            },
        )
        if Cookie.CSRFTOKEN not in request.COOKIES:
            csrf_token = csrf.get_token(request)
            response.set_cookie(Cookie.CSRFTOKEN, csrf_token)

        return response

    def set_user_organization(
        self, request: Request, organization_id: str
    ) -> Response:
        user: User = request.user
        new_organization = False
        organization_ids = CacheService.get_user_organizations(user.user_id)
        if not organization_ids:
            z_organizations: list[OrganizationData] = (
                self.auth_service.get_organizations_by_user_id(user.user_id)
            )
            organization_ids = {org.id for org in z_organizations}
        if organization_id and organization_id in organization_ids:
            organization = OrganizationService.get_organization_by_org_id(
                organization_id
            )
            if not organization:
                try:
                    organization_data: OrganizationData = (
                        self.auth_service.get_organization_by_org_id(
                            organization_id
                        )
                    )
                except ValueError:
                    raise OrganizationNotExist()
                try:
                    organization = OrganizationService.create_organization(
                        organization_data.name,
                        organization_data.display_name,
                        organization_data.id,
                    )
                    new_organization = True
                except IntegrityError:
                    raise DuplicateData(
                        f"{ErrorMessage.ORGANIZATION_EXIST}, \
                            {ErrorMessage.DUPLICATE_API}"
                    )
            self.create_tenant_user(organization=organization, user=user)

            if new_organization:
                try:
                    self.auth_service.frictionless_onboarding(
                        organization=organization, user=user
                    )
                except MethodNotImplemented:
                    Logger.info("Method not implemented")

            if new_organization:
                self.authentication_helper.create_initial_platform_key(
                    user=user, organization=organization
                )
            user_info: Optional[UserInfo] = self.get_user_info(request)
            serialized_user_info = SetOrganizationsResponseSerializer(
                user_info
            ).data
            organization_info = OrganizationSerializer(organization).data
            response: Response = Response(
                status=status.HTTP_200_OK,
                data={
                    "user": serialized_user_info,
                    "organization": organization_info,
                    f"{Common.LOG_EVENTS_ID}": StateStore.get(
                        Common.LOG_EVENTS_ID
                    ),
                },
            )
            # Update user session data in redis
            user_session_info: dict[str, Any] = (
                CacheService.get_user_session_info(user.email)
            )
            user_session_info["current_org"] = organization_id
            CacheService.set_user_session_info(user_session_info)
            response.set_cookie(Cookie.ORG_ID, organization_id)
            return response
        return Response(status=status.HTTP_403_FORBIDDEN)

    def get_user_info(self, request: Request) -> Optional[UserInfo]:
        return self.auth_service.get_user_info(request)

    def is_admin_by_role(self, role: str) -> bool:
        """Check the role is act as admin in the context of authentication
        plugin.

        Args:
            role (str): role

        Returns:
            bool: _description_
        """
        return self.auth_service.is_admin_by_role(role=role)

    def get_organization_info(self, org_id: str) -> Optional[Organization]:
        organization = self.auth_service.get_organization_info(org_id)
        if not organization:
            organization = OrganizationService.get_organization_by_org_id(
                org_id=org_id
            )
        return organization

    def make_organization_and_add_member(
        self,
        user_id: str,
        user_name: str,
        organization_name: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Optional[OrganizationData]:
        return self.auth_service.make_organization_and_add_member(
            user_id, user_name, organization_name, display_name
        )

    def make_user_organization_name(self) -> str:
        return self.auth_service.make_user_organization_name()

    def make_user_organization_display_name(self, user_name: str) -> str:
        return self.auth_service.make_user_organization_display_name(user_name)

    def user_logout(self, request: Request) -> Response:
        response = self.auth_service.user_logout(request=request)
        django_logout(request)
        return response

    def get_organization_members_by_org_id(
        self, organization_id: Optional[str] = None
    ) -> list[OrganizationMember]:
        members: list[OrganizationMember] = OrganizationMember.objects.all()
        return members

    def get_organization_members_by_user(
        self, user: User
    ) -> OrganizationMember:
        member: OrganizationMember = OrganizationMember.objects.filter(
            user=user
        ).first()
        return member

    def get_user_roles(self) -> list[UserRoleData]:
        return self.auth_service.get_roles()

    def get_user_invitations(
        self, organization_id: str
    ) -> list[MemberInvitation]:
        return self.auth_service.get_invitations(
            organization_id=organization_id
        )

    def delete_user_invitation(
        self, organization_id: str, invitation_id: str
    ) -> bool:
        return self.auth_service.delete_invitation(
            organization_id=organization_id, invitation_id=invitation_id
        )

    def reset_user_password(self, user: User) -> Response:
        return self.auth_service.reset_user_password(user)

    def invite_user(
        self,
        admin: User,
        org_id: str,
        user_list: list[dict[str, Union[str, None]]],
    ) -> list[UserInviteResponse]:
        """Invites users to join an organization.

        Args:
            admin (User): Admin user initiating the invitation.
            org_id (str): ID of the organization to which users are invited.
            user_list (list[dict[str, Union[str, None]]]):
                List of user details for invitation.
        Returns:
            list[UserInviteResponse]: List of responses for each
                user invitation.
        """
        admin_user = OrganizationMember.objects.get(user=admin.id)
        if not self.auth_service.is_organization_admin(admin_user):
            raise Forbidden()
        response = []
        for user_item in user_list:
            email = user_item.get("email")
            role = user_item.get("role")
            if email:
                user = self.organization_member_service.get_user_by_email(
                    email=email
                )
                user_response = {}
                user_response["email"] = email
                status = False
                message = "User is already part of current organization"
                # Check if user is already part of current organization
                if not user:
                    status = self.auth_service.invite_user(
                        admin_user, org_id, email, role=role
                    )
                    message = "User invitation successful."

                response.append(
                    UserInviteResponse(
                        email=email,
                        status="success" if status else "failed",
                        message=message,
                    )
                )
        return response

    def remove_users_from_organization(
        self, admin: User, organization_id: str, user_emails: list[str]
    ) -> bool:
        admin_user = OrganizationMember.objects.get(user=admin.id)
        user_ids = OrganizationMember.objects.filter(
            user__email__in=user_emails
        ).values_list(
            OrganizationMemberModel.USER_ID, OrganizationMemberModel.ID
        )
        user_ids_list: list[str] = []
        ids_list: list[str] = []
        for user in user_ids:
            user_ids_list.append(user[0])
            ids_list.append(user[1])
        if len(user_ids_list) > 0:
            is_removed = self.auth_service.remove_users_from_organization(
                admin=admin_user,
                organization_id=organization_id,
                user_ids=user_ids_list,
            )
        else:
            is_removed = False
        if is_removed:
            OrganizationMember.objects.filter(user__in=ids_list).delete()
            # removing adapter relations on user removal
            for user_id in ids_list:
                User.objects.get(pk=user_id).shared_adapters.clear()
        return is_removed

    def add_user_role(
        self, admin: User, org_id: str, email: str, role: str
    ) -> Optional[str]:
        admin_user = OrganizationMember.objects.get(user=admin.id)
        user = self.organization_member_service.get_user_by_email(email=email)
        if user:
            current_roles = self.auth_service.add_organization_user_role(
                admin_user, org_id, user.user.user_id, [role]
            )
            if current_roles:
                self.save_orgnanization_user_role(
                    user_id=user.user.user_id, role=current_roles[0]
                )
            return current_roles[0]
        else:
            return None

    def remove_user_role(
        self, admin: User, org_id: str, email: str, role: str
    ) -> Optional[str]:
        admin_user = OrganizationMember.objects.get(user=admin.id)
        organization_member = (
            self.organization_member_service.get_user_by_email(email=email)
        )
        if organization_member:
            current_roles = self.auth_service.remove_organization_user_role(
                admin_user, org_id, organization_member.user.user_id, [role]
            )
            if current_roles:
                self.save_orgnanization_user_role(
                    user_id=organization_member.user.user_id,
                    role=current_roles[0],
                )
            return current_roles[0]
        else:
            return None

    def save_orgnanization_user_role(self, user_id: str, role: str) -> None:
        organization_user = (
            self.organization_member_service.get_user_by_user_id(
                user_id=user_id
            )
        )
        if organization_user:
            # consider single role
            organization_user.role = role
            organization_user.save()

    def create_tenant_user(
        self, organization: Organization, user: User
    ) -> None:
        with tenant_context(organization):
            existing_tenant_user = (
                self.organization_member_service.get_user_by_id(id=user.id)
            )
            if existing_tenant_user:
                Logger.info(f"{existing_tenant_user.user.email} Already exist")
            else:
                account_user = self.get_or_create_user(user=user)
                if account_user:
                    user_roles = (
                        self.auth_service.get_organization_role_of_user(
                            user_id=account_user.user_id,
                            organization_id=organization.organization_id,
                        )
                    )
                    user_role = user_roles[0]
                    tenant_user: OrganizationMember = OrganizationMember(
                        user=user, role=user_role
                    )
                    tenant_user.save()
                else:
                    raise UserNotExistError()

    def get_or_create_user_by_email(
        self, request: Request, callback_data: CallbackData
    ) -> Union[User, OrganizationMember]:
        email = callback_data.email
        user_service = UserService()
        user = user_service.get_user_by_email(email)
        if not user:
            user_id = callback_data.user_id
            user = user_service.create_user(email, user_id)
        return user

    def get_or_create_user(
        self, user: User
    ) -> Optional[Union[User, OrganizationMember]]:
        user_service = UserService()
        if user.id:
            account_user: Optional[User] = user_service.get_user_by_id(user.id)
            if account_user:
                return account_user
            elif user.email:
                account_user = user_service.get_user_by_email(email=user.email)
                if account_user:
                    return account_user
                if user.user_id:
                    user.save()
                    return user
        elif user.email and user.user_id:
            account_user = user_service.create_user(
                email=user.email, user_id=user.user_id
            )
            return account_user
        return None
