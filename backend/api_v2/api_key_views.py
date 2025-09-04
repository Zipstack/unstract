from permissions.permission import IsOwnerOrSharedUser
from pipeline_v2.exceptions import PipelineNotFound
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import APINotFound, PathVariablesNotFound
from api_v2.key_helper import KeyHelper
from api_v2.models import APIKey
from api_v2.serializers import APIKeyListSerializer, APIKeySerializer


class APIKeyViewSet(viewsets.ModelViewSet):
    queryset = APIKey.objects.all()
    permission_classes = [IsOwnerOrSharedUser]

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action in ["api_keys"]:
            return APIKeyListSerializer
        return APIKeySerializer

    @action(detail=True, methods=["get"])
    def api_keys(
        self,
        request: Request,
        api_id: str | None = None,
        pipeline_id: str | None = None,
    ) -> Response:
        """Custom action to fetch api keys of an api deployment."""
        if api_id:
            api = DeploymentHelper.get_api_by_id(api_id=api_id)
            if not api:
                raise APINotFound()
            self.check_object_permissions(request, api)
            keys = KeyHelper.list_api_keys_of_api(api_instance=api)
        elif pipeline_id:
            pipeline = PipelineProcessor.get_active_pipeline(pipeline_id=pipeline_id)
            if not pipeline:
                raise PipelineNotFound()
            self.check_object_permissions(request, pipeline)
            keys = KeyHelper.list_api_keys_of_pipeline(pipeline_instance=pipeline)
        else:
            raise PathVariablesNotFound(
                "Either `api_id` or `pipeline_id` path variable must be provided."
            )
        serializer = self.get_serializer(keys, many=True)
        return Response(serializer.data)
