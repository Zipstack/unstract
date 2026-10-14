import uuid

from api_v2.models import APIDeployment
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import (
    best_effort,
    record_key_update,
    record_platform_event,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.user_context import UserContext

from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.permissions import IsOrganizationAdmin
from global_api_deployment_key.serializers import (
    ApiDeploymentMinimalSerializer,
    GlobalApiDeploymentKeyCreateSerializer,
    GlobalApiDeploymentKeyDetailSerializer,
    GlobalApiDeploymentKeyListSerializer,
    GlobalApiDeploymentKeyUpdateSerializer,
)


class GlobalApiDeploymentKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get_queryset(self):
        # ``created_by`` is select_related because the list serializer reads
        # ``created_by.email`` per row; without it the unpaginated list costs
        # one extra query per key.
        return (
            GlobalApiDeploymentKey.objects.filter(
                organization=UserContext.get_organization(),
            )
            .select_related("created_by")
            .prefetch_related("api_deployments")
        )

    def get_serializer_class(self):
        # create/retrieve/partial_update/rotate are overridden and instantiate
        # their serializers directly, so only ``list``/``destroy`` (and DRF's
        # default fallback) route through here — all use the list serializer.
        return GlobalApiDeploymentKeyListSerializer

    def create(self, request, *args, **kwargs):
        serializer = GlobalApiDeploymentKeyCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        _record_key_event(
            request,
            Action.KEY_CREATED,
            instance.id,
            instance.name,
            changes={"after": _key_fields(instance)},
        )
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        before = _key_fields(instance)
        serializer = GlobalApiDeploymentKeyUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_instance = serializer.save()
        _record_key_update(request, updated_instance, before)
        response_serializer = GlobalApiDeploymentKeyListSerializer(updated_instance)
        return Response(response_serializer.data)

    def rotate(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.key = uuid.uuid4()
        instance.modified_by = request.user
        instance.save(update_fields=["key", "modified_by", "modified_at"])
        _record_key_event(request, Action.KEY_ROTATED, instance.id, instance.name)
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data)

    def perform_destroy(self, instance):
        key_id, key_name, before = instance.id, instance.name, _key_fields(instance)
        instance.delete()
        _record_key_event(
            self.request, Action.KEY_REVOKED, key_id, key_name, changes={"before": before}
        )

    @action(detail=False, methods=["get"])
    def deployments(self, request):
        """List all API deployments in the org for admins to assign to keys."""
        organization = UserContext.get_organization()
        deployments = APIDeployment.objects.filter(organization=organization)
        serializer = ApiDeploymentMinimalSerializer(deployments, many=True)
        return Response(serializer.data)


@best_effort
def _key_fields(key: GlobalApiDeploymentKey) -> dict:
    """The audited fields. Never the key value itself."""
    return {
        "description": key.description,
        "is_active": key.is_active,
        "allow_all_deployments": key.allow_all_deployments,
        "api_deployments": sorted(
            str(pk) for pk in key.api_deployments.all().values_list("pk", flat=True)
        ),
    }


def _record_key_event(request, action: Action, key_id, key_name: str, **kwargs) -> None:
    record_platform_event(
        action=action,
        target_type=TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        target_id=key_id,
        target_name=key_name,
        request=request,
        **kwargs,
    )


@best_effort
def _record_key_update(request, key: GlobalApiDeploymentKey, before: dict) -> None:
    record_key_update(
        target_type=TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        key=key,
        before=before,
        after=_key_fields(key),
        request=request,
    )
