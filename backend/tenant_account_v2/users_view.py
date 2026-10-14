import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.exceptions import BadRequestException
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import (
    BEFORE_UNAVAILABLE,
    best_effort,
    record_platform_event,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_context import UserContext
from utils.user_session import UserSessionUtils

from tenant_account_v2.models import OrganizationMember
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tenant_account_v2.serializer import (
    ChangeUserRoleRequestSerializer,
    InviteUserSerializer,
    OrganizationMemberSerializer,
    RemoveUserFromOrganizationSerializer,
    UpdateFlagSerializer,
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
        org_id: str = UserSessionUtils.get_organization_id(request)
        auth_controller = AuthenticationController()

        auth_controller = AuthenticationController()
        member_before = _member_snapshot(user_email)
        update_status = auth_controller.add_user_role(request, org_id, user_email, role)
        if update_status:
            _record_role_change(request, user_email, member_before, update_status)
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
        member_before = _member_snapshot(user_email)
        update_status = auth_controller.remove_user_role(
            request, org_id, user_email, role
        )
        if update_status:
            _record_role_change(request, user_email, member_before, update_status)
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
            admin=request.user,
            org_id=UserSessionUtils.get_organization_id(request),
            user_list=user_list,
            request=request,
        )

        _record_invites(request, user_list, invite_response)
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
        members_before = [(e, _member_snapshot(e)) for e in user_emails]
        is_updated = auth_controller.remove_users_from_organization(
            request=request,
            organization_id=organization_id,
            user_emails=user_emails,
        )
        if is_updated:
            _record_removals(request, members_before)
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


# Returned for an e-mail with no membership, so that ``None`` (from
# ``best_effort``) means only "the lookup failed".
_NOT_A_MEMBER: dict = {}


@best_effort
def _member_snapshot(email: str) -> dict | None:
    member = OrganizationMemberService.get_user_by_email(email=email)
    if member is None:
        return _NOT_A_MEMBER
    return {"user_id": member.user_id, "email": member.user.email, "role": member.role}


@best_effort
def _record_role_change(
    request: Request, email: str, member_before: dict | None, new_role: str
) -> None:
    old_role = member_before["role"] if member_before else None
    if old_role == new_role:
        return
    record_platform_event(
        action=Action.MEMBER_ROLE_CHANGED,
        target_type=TargetType.MEMBER,
        target_id=member_before["user_id"] if member_before else "",
        target_name=member_before["email"] if member_before else email,
        changes={
            "before": {"role": old_role} if old_role else None,
            "after": {"role": new_role},
        },
        summary=f"{old_role} → {new_role}"
        if old_role
        else f"role → {new_role} {BEFORE_UNAVAILABLE}",
        request=request,
    )


@best_effort
def _record_invites(request: Request, user_list: list, invite_response: list) -> None:
    roles = {item.get("email"): item.get("role") for item in user_list}
    organization = UserContext.get_organization()  # once, not per event
    for invite in invite_response or []:
        if invite.status != "success":
            continue
        role = roles.get(invite.email)
        record_platform_event(
            action=Action.MEMBER_INVITED,
            target_type=TargetType.INVITATION,
            target_id=invite.email,
            target_name=invite.email,
            changes={"after": {"role": role}},
            summary=f"as {role}" if role else "",
            request=request,
            organization=organization,
        )


@best_effort
def _record_removals(
    request: Request, members_before: list[tuple[str, dict | None]]
) -> None:
    """One event per removed member. A member whose snapshot could not be read
    is still recorded, by e-mail and without ``before``.
    """
    organization = UserContext.get_organization()  # once, not per event
    for email, member in members_before:
        if member is _NOT_A_MEMBER:
            continue
        if member is None:
            record_platform_event(
                action=Action.MEMBER_REMOVED,
                target_type=TargetType.MEMBER,
                target_name=email,
                summary=BEFORE_UNAVAILABLE,
                request=request,
                organization=organization,
            )
            continue
        record_platform_event(
            action=Action.MEMBER_REMOVED,
            target_type=TargetType.MEMBER,
            target_id=member["user_id"],
            target_name=member["email"],
            changes={"before": {"role": member["role"]}},
            summary=f"was {member['role']}",
            request=request,
            organization=organization,
        )
