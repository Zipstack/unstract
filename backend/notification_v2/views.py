from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import APINotFound
from notification_v2.constants import NotificationUrlConstant
from pipeline_v2.exceptions import PipelineNotFound
from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import viewsets

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer

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
