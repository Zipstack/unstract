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
        """Create an API key for the deployment or pipeline being targeted.

        `POST keys/api/<api_id>/` and `POST keys/pipeline/<pipeline_id>/`
        already name the resource in the path, so callers need not repeat it
        in the body. The body-only routes (`keys/api/`, `keys/pipeline/`) name
        it in `api` / `pipeline` instead.

        Whichever route is used, the target is resolved and **ownership is
        checked here**, because `create` is collection-level: DRF resolves
        `IsParentDeploymentOwner` for it but never calls `get_object()`, so
        `has_object_permission` never runs on its own. Without this, any org
        member could mint a live key for a deployment they do not own. The
        check must cover the body-only routes too — otherwise the same hole is
        simply reachable by moving the identifier from the path into the body.

        The path target is authoritative: a body naming the *other* target is
        a contradiction, not an override, and is refused rather than silently
        creating a key for whichever one wins. A body repeating the *same*
        target with the *same* value is accepted and overwritten -- it agrees
        with the path, so there is nothing to refuse. A body naming the same
        field with a *different* value is refused for the same reason as the
        cross-type case: silently minting a key for the path's resource while
        the caller named another one is a wrong-resource credential, not a
        harmless override.
        """
        # A JSON array (or scalar) body has no `.copy()` returning a mapping;
        # reject it as a 400 rather than letting `AttributeError` become a 500.
        if not isinstance(request.data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": "Request body must be a JSON object."}
            )
        request_data = request.data.copy()

        api_id = kwargs.get("api_id")
        pipeline_id = kwargs.get("pipeline_id")

        if api_id and request_data.get("pipeline"):
            raise serializers.ValidationError(
                {
                    "pipeline": "This endpoint creates a key for the API "
                    "deployment named in the URL; remove `pipeline` from the body."
                }
            )
        if pipeline_id and request_data.get("api"):
            raise serializers.ValidationError(
                {
                    "api": "This endpoint creates a key for the pipeline named "
                    "in the URL; remove `api` from the body."
                }
            )

        # Same field, different value: the caller named one resource in the
        # path and another in the body. Overwriting silently would mint a live
        # key for a resource they did not ask for -- refuse, as for the
        # cross-type contradictions above. An empty body value is not a
        # disagreement; it simply does not name anything.
        for field, path_value in (("api", api_id), ("pipeline", pipeline_id)):
            body_value = request_data.get(field)
            if path_value and body_value and str(body_value) != str(path_value):
                raise serializers.ValidationError(
                    {
                        field: f"`{field}` in the body names a different resource "
                        "than the URL; remove it or make the two agree."
                    }
                )

        # The path wins where it names a target; otherwise fall back to the
        # body, so the body-only routes resolve to the same guarded path.
        api_id = api_id or request_data.get("api")
        pipeline_id = pipeline_id or request_data.get("pipeline")

        if api_id:
            api = DeploymentHelper.get_api_by_id(api_id=api_id)
            if not api:
                raise APINotFound()
            self.check_object_permissions(request, api)
            request_data["api"] = api_id
        elif pipeline_id:
            # `check_active=False`: minting a key does not require a running
            # pipeline, and `get_active_pipeline` would both 422 on a paused
            # one and disclose its state before the ownership check below.
            pipeline = PipelineProcessor.get_pipeline_by_id(pipeline_id=pipeline_id)
            if not pipeline:
                raise PipelineNotFound()
            self.check_object_permissions(request, pipeline)
            request_data["pipeline"] = pipeline_id
        # Neither named: let the serializer raise its "one of api/pipeline"
        # error rather than inventing a second wording for the same condition.

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
