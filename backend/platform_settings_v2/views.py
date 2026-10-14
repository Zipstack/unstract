# views.py

import logging
from typing import Any

from account_v2.models import Organization, PlatformKey
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import best_effort, record_platform_event
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from utils.user_context import UserContext

from platform_settings_v2.constants import PlatformServiceConstants
from platform_settings_v2.platform_auth_helper import PlatformAuthHelper
from platform_settings_v2.platform_auth_service import PlatformAuthenticationService
from platform_settings_v2.serializers import (
    PlatformKeyGenerateSerializer,
    PlatformKeyIDSerializer,
    PlatformKeySerializer,
)

logger = logging.getLogger(__name__)


class PlatformKeyViewSet(viewsets.ModelViewSet):
    serializer_class = PlatformKeySerializer

    def get_queryset(self):
        return PlatformKey.objects.all()

    def validate_user_role(func: Any) -> Any:
        def wrapper(
            self: Any,
            request: Request,
            *args: tuple[Any],
            **kwargs: dict[str, Any],
        ) -> Any:
            PlatformAuthHelper.validate_user_role(request.user)
            return func(self, request, *args, **kwargs)

        return wrapper

    @validate_user_role
    def list(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        platform_key_ids = PlatformAuthenticationService.list_platform_key_ids()
        serializer = PlatformKeyIDSerializer(platform_key_ids, many=True)
        return Response(
            status=status.HTTP_200_OK,
            data=serializer.data,
        )

    @validate_user_role
    def refresh(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        """API Endpoint for refreshing platform keys."""
        id = request.data.get(PlatformServiceConstants.ID)
        if not id:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    "message": "validation error",
                    "errors": "Mandatory fields missing",
                },
            )
        platform_key = PlatformAuthenticationService.refresh_platform_key(
            id=id, user=request.user
        )
        _record_key_result(request, Action.KEY_ROTATED, platform_key)
        return Response(
            status=status.HTTP_201_CREATED,
            data=platform_key,
        )

    @validate_user_role
    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        instance = self.get_object()
        key_id, key_name = instance.id, instance.key_name
        instance.delete()
        _record_key_event(request, Action.KEY_REVOKED, key_id, key_name)
        return Response(
            status=status.HTTP_204_NO_CONTENT,
            data={"message": "Platform key deleted successfully"},
        )

    @validate_user_role
    def toggle_platform_key(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        instance = self.get_object()
        action = request.data.get(PlatformServiceConstants.ACTION)
        if not action:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    "message": "validation error",
                    "errors": "Mandatory fields missing",
                },
            )
        was_active, others_active = instance.is_active, _active_keys(exclude=instance)
        PlatformAuthenticationService.toggle_platform_key_status(
            platform_key=instance, action=action, user=request.user
        )
        _record_toggle(request, instance, was_active, others_active)
        return Response(
            status=status.HTTP_201_CREATED,
            data={"message": "Platform key toggled successfully"},
        )

    @validate_user_role
    def create(self, request: Request) -> Response:
        serializer = PlatformKeyGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_active = request.data.get(PlatformServiceConstants.IS_ACTIVE)
        key_name = request.data.get(PlatformServiceConstants.KEY_NAME)
        organization: Organization = UserContext.get_organization()

        PlatformAuthHelper.validate_token_count(organization=organization)

        platform_key = PlatformAuthenticationService.generate_platform_key(
            is_active=is_active, key_name=key_name, user=request.user
        )
        _record_key_result(
            request,
            Action.KEY_CREATED,
            platform_key,
            changes={"after": {"is_active": bool(is_active)}},
        )
        serialized_data = self.serializer_class(platform_key).data
        return Response(
            status=status.HTTP_201_CREATED,
            data=serialized_data,
        )


def _record_key_event(request: Request, action: Action, key_id, key_name, **kwargs):
    record_platform_event(
        action=action,
        target_type=TargetType.PLATFORM_KEY,
        target_id=key_id,
        target_name=key_name or "",
        request=request,
        **kwargs,
    )


@best_effort
def _record_key_result(request: Request, action: Action, result: dict, **kwargs):
    """For the service calls that return the key as a dict."""
    _record_key_event(
        request,
        action,
        result[PlatformServiceConstants.ID],
        result.get(PlatformServiceConstants.KEY_NAME),
        **kwargs,
    )


@best_effort
def _active_keys(exclude: PlatformKey) -> list[tuple]:
    """Other active keys; activating one key deactivates every other."""
    return list(
        PlatformKey.objects.filter(
            organization=UserContext.get_organization(), is_active=True
        )
        .exclude(pk=exclude.pk)
        .values_list("id", "key_name")
    )


@best_effort
def _record_toggle(
    request: Request, key: PlatformKey, was_active: bool, others_active: list | None
):
    if key.is_active:
        if not was_active:
            _record_key_event(request, Action.KEY_ENABLED, key.id, key.key_name)
        # Activating deactivates every other active key, even when this key
        # was already active.
        for other_id, other_name in others_active or []:
            _record_key_event(
                request,
                Action.KEY_DISABLED,
                other_id,
                other_name,
                summary=f"deactivated when {key.key_name} was activated",
            )
    elif was_active:
        _record_key_event(request, Action.KEY_DISABLED, key.id, key.key_name)
