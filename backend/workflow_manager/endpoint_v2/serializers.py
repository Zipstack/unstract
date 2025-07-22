import logging

from rest_framework.serializers import ModelSerializer
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

logger = logging.getLogger(__name__)


class WorkflowEndpointSerializer(ModelSerializer):
    class Meta:
        model = WorkflowEndpoint
        fields = "__all__"
