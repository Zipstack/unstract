"""Internal API views for group-sharing email notifications (UN-3494 / UNS-848).

Mounted under ``/internal/`` and gated by ``InternalAPIAuthMiddleware``. The
notification worker calls these because ``workers/`` has no Django and every
step of the send — group expansion, org re-validation, resource lookup, the
email plugin — needs it.

Failure contract: **any** unhandled problem must surface as non-2xx so the
queue redelivers. The one deliberate exception is a resource that no longer
exists, which returns 200 — retrying that can only fail again.
"""

import logging

from account_v2.models import Organization
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.user_context import UserContext

from tenant_account_v2.group_notification_service import (
    ResourceNotFoundError,
    send_membership_changed,
    send_resource_shared,
)
from tenant_account_v2.share_notifications import MembershipAction

logger = logging.getLogger(__name__)


class ResourceSharedWithGroupSerializer(serializers.Serializer):
    """Payload of ``notify_resource_shared_with_group``."""

    group_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    actor_id = serializers.IntegerField()
    resource_kind = serializers.CharField()
    resource_id = serializers.CharField()


class GroupMembershipChangedSerializer(serializers.Serializer):
    """Payload of ``notify_group_membership_changed``."""

    group_id = serializers.IntegerField()
    actor_id = serializers.IntegerField()
    membership_action = serializers.ChoiceField(
        choices=[a.value for a in MembershipAction]
    )
    user_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class _GroupNotificationView(APIView):
    """Shared org resolution for the group-notification endpoints."""

    @staticmethod
    def _organization() -> Organization:
        organization = UserContext.get_organization()
        if organization is None:
            raise ValidationError(
                "Organization context missing. Worker must send X-Organization-ID."
            )
        return organization


class ResourceSharedWithGroupView(_GroupNotificationView):
    """Mail every current member of the groups a resource was just shared with."""

    def post(self, request: Request) -> Response:
        serializer = ResourceSharedWithGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            send_resource_shared(organization=self._organization(), **data)
        except ResourceNotFoundError as exc:
            # Deleted between the share and the send — a retry cannot help.
            logger.info("group-notification: dropping resource share (%s)", exc)
            return Response({"status": "skipped"}, status=status.HTTP_200_OK)
        return Response({"status": "success"}, status=status.HTTP_200_OK)


class GroupMembershipChangedView(_GroupNotificationView):
    """Mail the users whose group membership just changed."""

    def post(self, request: Request) -> Response:
        serializer = GroupMembershipChangedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        send_membership_changed(
            organization=self._organization(), **serializer.validated_data
        )
        return Response({"status": "success"}, status=status.HTTP_200_OK)
