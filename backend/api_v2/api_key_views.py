from typing import Any

from permissions.permission import IsOwnerOrSharedUser, IsParentDeploymentOwner
from pipeline_v2.exceptions import PipelineNotFound
from pipeline_v2.pipeline_processor import PipelineProcessor
from rest_framework import serializers, status, viewsets
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

    def get_permissions(self) -> list[Any]:
        # ``api_keys`` object-checks the parent deployment/pipeline directly
        # and stays viewer-readable. Every other detail action reveals or
        # mutates a key, so it is gated on the parent's owner — the ``APIKey``
        # row itself has no memberships, and checking it directly crashed on
        # the ``shared_users`` fallback for any non-creator (UN-2202).
        if self.action == "api_keys":
            return [IsOwnerOrSharedUser()]
        return [IsParentDeploymentOwner()]

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action in ["api_keys"]:
            return APIKeyListSerializer
        return APIKeySerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create an API key, deriving the target from the URL.

        `POST keys/api/<api_id>/` and `POST keys/pipeline/<pipeline_id>/`
        already name the resource in the path, so callers should not have to
        repeat it in the body. Fall back to whatever the body carries, keeping
        the body-only routes (`keys/api/`, `keys/pipeline/`) working.
        """
        api_id = kwargs.get("api_id")
        pipeline_id = kwargs.get("pipeline_id")

        if api_id or pipeline_id:
            request_data = request.data.copy()
            if api_id:
                request_data.setdefault("api", api_id)
            if pipeline_id:
                request_data.setdefault("pipeline", pipeline_id)
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )

        return super().create(request, *args, **kwargs)

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
