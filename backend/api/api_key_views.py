from api.deployment_helper import DeploymentHelper
from api.exceptions import APINotFound
from api.key_helper import KeyHelper
from api.models import APIKey
from api.serializers import APIKeyListSerializer, APIKeySerializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response


class APIKeyViewSet(viewsets.ModelViewSet):
    queryset = APIKey.objects.all()

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action in ["api_keys"]:
            return APIKeyListSerializer
        return APIKeySerializer

    @action(detail=True, methods=["get"])
    def api_keys(self, request: Request, api_id: str) -> Response:
        """Custom action to fetch api keys of an api deployment."""
        api = DeploymentHelper.get_api_by_id(api_id=api_id)
        if not api:
            raise APINotFound()
        keys = KeyHelper.list_api_keys_of_api(api_instance=api)
        serializer = self.get_serializer(keys, many=True)
        return Response(serializer.data)
