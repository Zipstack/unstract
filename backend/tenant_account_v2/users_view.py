import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.exceptions import BadRequestException
from account_v2.models import User
from account_v2.user_profile import delete_photo, photo_url, read_photo, save_photo
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_session import UserSessionUtils

from tenant_account_v2.models import OrganizationMember
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tenant_account_v2.serializer import (
    ChangeUserRoleRequestSerializer,
    InviteUserSerializer,
    OrganizationMemberSerializer,
    ProfilePhotoSerializer,
    ProfileUpdateSerializer,
    RemoveUserFromOrganizationSerializer,
    UpdateFlagSerializer,
    UserInfoSerializer,
    UserInviteResponseSerializer,
    UserProfileSerializer,
)

Logger = logging.getLogger(__name__)

PROFILE_RESPONSE = inline_serializer(
    "UserProfileResponse", {"user": UserProfileSerializer()}
)
PHOTO_URL_RESPONSE = inline_serializer(
    "UserProfilePhotoResponse", {"photo_url": serializers.CharField()}
)


class OrganizationUserViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["POST"])
    def assign_organization_role_to_user(self, request: Request) -> Response:
        serializer = ChangeUserRoleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_email = serializer.get_user_email(serializer.validated_data)
        role = serializer.get_user_role(serializer.validated_data)
        if not (user_email and role):
            raise BadRequestException
        org_id: str = UserSessionUtils.get_organization_id(request)
        auth_controller = AuthenticationController()

        auth_controller = AuthenticationController()
        update_status = auth_controller.add_user_role(request, org_id, user_email, role)
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
        org_id: str = UserSessionUtils.get_organization_id(request)
        auth_controller = AuthenticationController()

        auth_controller = AuthenticationController()
        update_status = auth_controller.remove_user_role(
            request, org_id, user_email, role
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

    @extend_schema(
        operation_id="user_profile",
        tags=["profile"],
        responses={200: PROFILE_RESPONSE},
        description="The current user. See tenant_account_v2/ReadMe.md.",
    )
    @action(detail=False, methods=["GET"])
    def get_user_profile(self, request: Request) -> Response:
        auth_controller = AuthenticationController()
        try:
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
            serialized_user_info["is_admin"] = auth_controller.is_admin_by_role(role.role)
            # changes for displying onboarding msgs
            org_member = OrganizationMemberService.get_user_by_id(id=request.user.id)
            serialized_user_info["login_onboarding_message_displayed"] = (
                org_member.is_login_onboarding_msg
            )
            serialized_user_info["prompt_onboarding_message_displayed"] = (
                org_member.is_prompt_studio_onboarding_msg
            )

            # Add role and organization details
            serialized_user_info["role"] = role.role

            org_id = UserSessionUtils.get_organization_id(request)
            if org_id:
                org = auth_controller.get_organization_info(org_id)
                if org:
                    serialized_user_info["organization_name"] = org.display_name
                    serialized_user_info["organization_id"] = org.organization_id
            serialized_user_info["photo_url"] = photo_url(request.user, org_id)
            serialized_user_info["language"] = request.user.language

            return Response(
                status=status.HTTP_200_OK, data={"user": serialized_user_info}
            )
        except Exception as error:
            Logger.error(f"Error while get User : {error}")
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"message": "Internal Error"},
            )

    @extend_schema(
        operation_id="user_profile_update",
        tags=["profile"],
        request=ProfileUpdateSerializer,
        responses={
            200: PROFILE_RESPONSE,
            400: OpenApiResponse(description="Invalid field"),
        },
    )
    @action(detail=False, methods=["PATCH"])
    def update_profile(self, request: Request) -> Response:
        """Set the name and/or language shown for the current user."""
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = {
            "profile_display_name" if field == "display_name" else field: value
            for field, value in serializer.validated_data.items()
        }
        if changes:
            User.objects.filter(pk=request.user.pk).update(**changes)
            request.user.refresh_from_db(fields=list(changes))
        return self.get_user_profile(request)

    @extend_schema(
        operation_id="user_profile_photo",
        tags=["profile"],
        responses={
            (200, "image/png"): OpenApiTypes.BINARY,
            (200, "image/jpeg"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="No photo"),
        },
    )
    @action(detail=False, methods=["GET"])
    def get_profile_photo(self, request: Request) -> HttpResponse:
        photo = read_photo(request.user)
        if not photo:
            raise NotFound("No profile photo.")
        data, content_type = photo
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = "inline"
        return response

    @extend_schema(
        operation_id="user_profile_photo_upload",
        tags=["profile"],
        request={"multipart/form-data": ProfilePhotoSerializer},
        responses={
            200: PHOTO_URL_RESPONSE,
            400: OpenApiResponse(description="Not a PNG or JPEG, or over 2 MB"),
        },
    )
    @action(detail=False, methods=["POST"])
    def upload_profile_photo(self, request: Request) -> Response:
        serializer = ProfilePhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        save_photo(request.user, serializer.validated_data["photo"].read())
        org_id = UserSessionUtils.get_organization_id(request)
        return Response(
            status=status.HTTP_200_OK,
            data={"photo_url": photo_url(request.user, org_id)},
        )

    @extend_schema(
        operation_id="user_profile_photo_delete",
        tags=["profile"],
        responses={204: None},
    )
    @action(detail=False, methods=["DELETE"])
    def delete_profile_photo(self, request: Request) -> Response:
        delete_photo(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["POST"])
    def invite_user(self, request: Request) -> Response:
        serializer = InviteUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_list = serializer.get_users(serializer.validated_data)
        auth_controller = AuthenticationController()
        invite_response = auth_controller.invite_user(
            admin=request.user,
            org_id=UserSessionUtils.get_organization_id(request),
            user_list=user_list,
            request=request,
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
        organization_id: str = UserSessionUtils.get_organization_id(request)

        auth_controller = AuthenticationController()
        is_updated = auth_controller.remove_users_from_organization(
            request=request,
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
        if UserSessionUtils.get_organization_id(request):
            members: list[OrganizationMember] = (
                auth_controller.get_organization_members_by_org_id()
            )
            serialized_members = OrganizationMemberSerializer(
                members, many=True, context={"auth_controller": auth_controller}
            ).data
            return Response(
                status=status.HTTP_200_OK,
                data={"message": "success", "members": serialized_members},
            )
        return Response(
            status=status.HTTP_401_UNAUTHORIZED,
            data={"message": "cookie not found"},
        )

    @action(detail=False, methods=["PUT"])
    def update_flags(self, request: Request) -> Response:
        serializer = UpdateFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org_member = OrganizationMemberService.get_user_by_id(id=request.user.id)
        org_member.is_login_onboarding_msg = serializer.validated_data.get(
            "is_login_onboarding_msg"
        )

        org_member.is_prompt_studio_onboarding_msg = serializer.validated_data.get(
            "is_prompt_studio_onboarding_msg"
        )
        org_member.save()
        return Response(
            status=status.HTTP_200_OK,
            data={"status": "success", "message": "success"},
        )
