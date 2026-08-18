import logging

from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import APINotFound
from configuration.enums import ConfigKey
from configuration.models import Configuration
from pipeline_v2.exceptions import PipelineNotFound
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from platform_api.permissions import IsOrganizationAdmin
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.user_context import UserContext

from notification_v2.constants import NotificationUrlConstant

from .models import Notification
from .serializers import NotificationSerializer, NotificationSettingsSerializer

logger = logging.getLogger(__name__)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    org_filter_paths = [
        "pipeline__workflow__organization",
        "api__workflow__organization",
    ]

    def get_queryset(self):
        queryset = Notification.objects.all()
        pipeline_uuid = self.kwargs.get(NotificationUrlConstant.PIPELINE_UID)
        api_uuid = self.kwargs.get(NotificationUrlConstant.API_UID)

        if pipeline_uuid:
            try:
                pipeline = PipelineProcessor.fetch_pipeline(
                    pipeline_id=pipeline_uuid, check_active=False
                )
                queryset = queryset.filter(pipeline=pipeline)
            except Pipeline.DoesNotExist:
                raise PipelineNotFound()

        elif api_uuid:
            api = DeploymentHelper.get_api_by_id(api_id=api_uuid)
            if not api:
                raise APINotFound()
            queryset = queryset.filter(api=api)

        return queryset


class NotificationSettingsView(APIView):
    """Org-scoped notification batching settings — currently just the club interval.

    GET returns the org's effective interval (override or env-derived default).
    PATCH writes/updates the override via the generic configuration KV table.

    Read-at-enqueue contract: updates take effect for notifications enqueued
    after the change. Existing PENDING buffer rows keep their original
    flush_after.
    """

    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get(self, request: Request) -> Response:
        organization = UserContext.get_organization()
        value = Configuration.get_value_by_organization(
            ConfigKey.NOTIFICATION_CLUB_INTERVAL, organization
        )
        return Response({"club_interval_seconds": int(value)})

    def patch(self, request: Request) -> Response:
        serializer = NotificationSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        organization = UserContext.get_organization()
        new_value = serializer.validated_data.get("club_interval_seconds")
        if new_value is None:
            return Response(
                {"detail": "club_interval_seconds is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # ConfigKey.cast_value enforces type + any future bounds; bubble its
        # ValueError up as a 400 instead of letting it 500.
        try:
            ConfigKey.NOTIFICATION_CLUB_INTERVAL.cast_value(new_value)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        Configuration.objects.update_or_create(
            organization=organization,
            key=ConfigKey.NOTIFICATION_CLUB_INTERVAL.name,
            defaults={"value": str(new_value), "enabled": True},
        )
        return Response({"club_interval_seconds": int(new_value)})
