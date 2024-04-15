import logging

from account.authentication_controller import AuthenticationController
from account.exceptions import BadRequestException
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account.models import OrganizationMember
from tenant_account.serializer import (
    ChangeUserRoleRequestSerializer,
    InviteUserSerializer,
    OrganizationMemberSerializer,
    RemoveUserFromOrganizationSerializer,
    UserInfoSerializer,
    UserInviteResponseSerializer,
)

Logger = logging.getLogger(__name__)


class OrganizationUserViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["POST"])
    def assign_organization_role_to_user(self, request: Request) -> Response:
        serializer = ChangeUserRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_email = serializer.get_user_email(serializer.validated_data)
        role = serializer.get_user_role(serializer.validated_data)
        if not (user_email and role):
            raise BadRequestException
        org_id: str = request.org_id
        auth_controller = AuthenticationController()

        auth_controller = AuthenticationController()
        update_status = auth_controller.add_user_role(
            request.user, org_id, user_email, role
        )
        if update_status:
            return Response(
                status=status.HTTP_200_OK,
                data={"status": "success", "message": "success"},
            )
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"status": "failed", "message": "failed"},
            )

    @action(detail=False, methods=["DELETE"])
    def remove_organization_role_from_user(self, request: Request) -> Response:
        serializer = ChangeUserRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_email = serializer.get_user_email(serializer.validated_data)
        role = serializer.get_user_role(serializer.validated_data)
        if not (user_email and role):
            raise BadRequestException
        org_id: str = request.org_id
        auth_controller = AuthenticationController()

        auth_controller = AuthenticationController()
        update_status = auth_controller.remove_user_role(
            request.user, org_id, user_email, role
        )
        if update_status:
            return Response(
                status=status.HTTP_200_OK,
                data={"status": "success", "message": "success"},
            )
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"status": "failed", "message": "failed"},
            )

    @action(detail=False, methods=["GET"])
    def get_user_profile(self, request: Request) -> Response:
        auth_controller = AuthenticationController()
        try:
            # z_code = request.COOKIES.get(Cookie.Z_CODE)
            user_info = auth_controller.get_user_info(request)
            role = auth_controller.get_organization_members_by_user(request.user)
            if not user_info:
                return Response(
                    status=status.HTTP_404_NOT_FOUND,
                    data={"message": "User Not Found"},
                )
            serialized_user_info = UserInfoSerializer(user_info).data
            # Temporary fix for getting user role along with user info.
            # Proper implementation would be adding role field to UserInfo.
            serialized_user_info["is_admin"] = auth_controller.is_admin_by_role(
                role.role
            )
            return Response(
                status=status.HTTP_200_OK, data={"user": serialized_user_info}
            )
        except Exception as error:
            Logger.error(f"Error while get User : {error}")
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"message": "Internal Error"},
            )

    @action(detail=False, methods=["POST"])
    def invite_user(self, request: Request) -> Response:
        serializer = InviteUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_list = serializer.get_users(serializer.validated_data)
        auth_controller = AuthenticationController()
        invite_response = auth_controller.invite_user(
            admin=request.user, org_id=request.org_id, user_list=user_list
        )

        response_serializer = UserInviteResponseSerializer(invite_response, many=True)

        if invite_response and len(invite_response) != 0:
            response = Response(
                status=status.HTTP_200_OK,
                data={"message": response_serializer.data},
            )
        else:
            response = Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"message": "failed"},
            )
        return response

    @action(detail=False, methods=["DELETE"])
    def remove_members_from_organization(self, request: Request) -> Response:
        serializer = RemoveUserFromOrganizationSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        user_emails = serializer.get_user_emails(serializer.validated_data)
        organization_id: str = request.org_id

        auth_controller = AuthenticationController()
        is_updated = auth_controller.remove_users_from_organization(
            admin=request.user,
            organization_id=organization_id,
            user_emails=user_emails,
        )
        if is_updated:
            return Response(
                status=status.HTTP_200_OK,
                data={"status": "success", "message": "success"},
            )
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"status": "failed", "message": "failed"},
            )

    @action(detail=False, methods=["GET"])
    def get_organization_members(self, request: Request) -> Response:
        auth_controller = AuthenticationController()
        if request.org_id:
            members: list[OrganizationMember] = (
                auth_controller.get_organization_members_by_org_id()
            )
            serialized_members = OrganizationMemberSerializer(members, many=True).data
            return Response(
                status=status.HTTP_200_OK,
                data={"message": "success", "members": serialized_members},
            )
        return Response(
            status=status.HTTP_401_UNAUTHORIZED,
            data={"message": "cookie not found"},
        )
