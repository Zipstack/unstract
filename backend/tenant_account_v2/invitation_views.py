import logging

from account_v2.authentication_controller import AuthenticationController
from account_v2.dto import MemberInvitation
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import best_effort, record_platform_event
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
        organization_id = UserSessionUtils.get_organization_id(request)
        invitee_email = _invitation_email(auth_controller, organization_id, id)
        is_deleted: bool = auth_controller.delete_user_invitation(
            organization_id=organization_id,
            invitation_id=id,
        )
        if is_deleted:
            record_platform_event(
                action=Action.INVITATION_REVOKED,
                target_type=TargetType.INVITATION,
                target_id=id,
                target_name=invitee_email or id,
                request=request,
            )
            return Response(
                status=status.HTTP_204_NO_CONTENT,
                data={"status": "success", "message": "success"},
            )
        else:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"status": "failed", "message": "failed"},
            )


@best_effort
def _invitation_email(
    auth_controller: AuthenticationController, organization_id: str, invitation_id: str
) -> str | None:
    """The invitee's e-mail, so the audit row names a person rather than an id.

    The delete call only takes the id, so this costs one extra lookup.
    """
    for invitation in auth_controller.get_user_invitations(organization_id):
        if str(invitation.id) == str(invitation_id):
            return invitation.email
    return None
