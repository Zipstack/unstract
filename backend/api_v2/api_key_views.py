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
        repeat it in the body. The body-only routes (`keys/api/`,
        `keys/pipeline/`) fall through to the default implementation.

        The path target is authoritative: a body naming the *other* target is
        a contradiction, not an override, and is refused rather than silently
        creating a key for whichever one wins. Ownership of the target is
        checked here because `create` is collection-level -- DRF resolves
        `IsParentDeploymentOwner` for it but never calls `get_object()`, so
        `has_object_permission` would otherwise never run and any org member
        could mint a live key for a deployment they do not own.
        """
        api_id = kwargs.get("api_id")
        pipeline_id = kwargs.get("pipeline_id")

        if not (api_id or pipeline_id):
            return super().create(request, *args, **kwargs)

        # A JSON array (or scalar) body has no `.copy()` returning a mapping;
        # reject it as a 400 rather than letting `AttributeError` become a 500.
        if not isinstance(request.data, dict):
            raise serializers.ValidationError("Request body must be a JSON object.")
        request_data = request.data.copy()

        if api_id:
            if request_data.get("pipeline"):
                raise serializers.ValidationError(
                    "This endpoint creates a key for the API deployment named "
                    "in the URL; remove `pipeline` from the body."
                )
            api = DeploymentHelper.get_api_by_id(api_id=api_id)
            if not api:
                raise APINotFound()
            self.check_object_permissions(request, api)
            request_data["api"] = api_id
        else:
            if request_data.get("api"):
                raise serializers.ValidationError(
                    "This endpoint creates a key for the pipeline named in the "
                    "URL; remove `api` from the body."
                )
            pipeline = PipelineProcessor.get_active_pipeline(pipeline_id=pipeline_id)
            if not pipeline:
                raise PipelineNotFound()
            self.check_object_permissions(request, pipeline)
            request_data["pipeline"] = pipeline_id

        serializer = self.get_serializer(data=request_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
