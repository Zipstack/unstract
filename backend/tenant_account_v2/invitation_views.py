import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import MemberInvitation
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_session import UserSessionUtils

from tenant_account_v2.serializer import ListInvitationsResponseSerializer

Logger = logging.getLogger(__name__)


class InvitationViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["GET"])
    def list_invitations(self, request: Request) -> Response:
        auth_controller = AuthenticationController()
        invitations: list[MemberInvitation] = auth_controller.get_user_invitations(
            organization_id=UserSessionUtils.get_organization_id(request),
        )
        serialized_members = ListInvitationsResponseSerializer(
            invitations, many=True
        ).data
        return Response(
            status=status.HTTP_200_OK,
            data={"message": "success", "members": serialized_members},
        )

    @action(detail=False, methods=["DELETE"])
    def delete_invitation(self, request: Request, id: str) -> Response:
        auth_controller = AuthenticationController()
        is_deleted: bool = auth_controller.delete_user_invitation(
            organization_id=UserSessionUtils.get_organization_id(request),
            invitation_id=id,
        )
        if is_deleted:
            return Response(
                status=status.HTTP_204_NO_CONTENT,
                data={"status": "success", "message": "success"},
            )
        else:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"status": "failed", "message": "failed"},
            )
