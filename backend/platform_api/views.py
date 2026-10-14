import uuid

from django.db import transaction
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import (
    best_effort,
    record_key_update,
    record_platform_event,
)
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.user_context import UserContext

from platform_api.models import PlatformApiKey
from platform_api.permissions import CanRotatePlatformApiKey, IsOrganizationAdmin
from platform_api.serializers import (
    PlatformApiKeyCreateSerializer,
    PlatformApiKeyDetailSerializer,
    PlatformApiKeyListSerializer,
    PlatformApiKeyUpdateSerializer,
)
from platform_api.services import create_api_user_for_key


class PlatformApiKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get_permissions(self):
        # Rotate allows self-service rotation by a platform API key (UN-3586);
        # all other key-management actions stay admin/session-only.
        if self.action == "rotate":
            return [IsAuthenticated(), CanRotatePlatformApiKey()]
        return super().get_permissions()

    def get_queryset(self):
        return PlatformApiKey.objects.filter(
            organization=UserContext.get_organization(),
        )

    def get_serializer_class(self):
        if self.action == "list":
            return PlatformApiKeyListSerializer
        if self.action == "create":
            return PlatformApiKeyCreateSerializer
        if self.action == "partial_update":
            return PlatformApiKeyUpdateSerializer
        return PlatformApiKeyListSerializer

    def create(self, request, *args, **kwargs):
        organization = UserContext.get_organization()

        serializer = PlatformApiKeyCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            platform_api_key = serializer.save()
            create_api_user_for_key(platform_api_key, organization)

        _record_key_event(
            request,
            Action.KEY_CREATED,
            platform_api_key.id,
            platform_api_key.name,
            changes={"after": _key_fields(platform_api_key)},
        )
        response_serializer = PlatformApiKeyDetailSerializer(platform_api_key)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = PlatformApiKeyDetailSerializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        before = _key_fields(instance)

        serializer = PlatformApiKeyUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_instance = serializer.save()
        _record_key_update(request, updated_instance, before)

        response_serializer = PlatformApiKeyListSerializer(updated_instance)
        return Response(response_serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        key_id, key_name, before = instance.id, instance.name, _key_fields(instance)
        instance.delete()
        _record_key_event(
            request, Action.KEY_REVOKED, key_id, key_name, changes={"before": before}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def rotate(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.key = uuid.uuid4()
        instance.modified_by = request.user
        instance.save(update_fields=["key", "modified_by"])
        _record_key_event(request, Action.KEY_ROTATED, instance.id, instance.name)

        response_serializer = PlatformApiKeyDetailSerializer(instance)
        return Response(response_serializer.data)


def _key_fields(key: PlatformApiKey) -> dict:
    """The audited fields. Never the key value itself."""
    return {
        "description": key.description,
        "is_active": key.is_active,
        "permission": key.permission,
    }


def _record_key_event(request, action: Action, key_id, key_name: str, **kwargs) -> None:
    record_platform_event(
        action=action,
        target_type=TargetType.PLATFORM_API_KEY,
        target_id=key_id,
        target_name=key_name,
        request=request,
        **kwargs,
    )


@best_effort
def _record_key_update(request, key: PlatformApiKey, before: dict) -> None:
    record_key_update(
        target_type=TargetType.PLATFORM_API_KEY,
        key=key,
        before=before,
        after=_key_fields(key),
        request=request,
    )
