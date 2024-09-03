# views.py

import logging
from typing import Any

from account.models import Organization, PlatformKey
from django.db import connection
from platform_settings.constants import PlatformServiceConstants
from platform_settings.platform_auth_helper import PlatformAuthHelper
from platform_settings.platform_auth_service import PlatformAuthenticationService
from platform_settings.serializers import (
    PlatformKeyGenerateSerializer,
    PlatformKeyIDSerializer,
    PlatformKeySerializer,
)
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class PlatformKeyViewSet(viewsets.ModelViewSet):
    queryset = PlatformKey.objects.all()
    serializer_class = PlatformKeySerializer

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
        return Response(
            status=status.HTTP_201_CREATED,
            data=platform_key,
        )

    @validate_user_role
    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        instance = self.get_object()
        instance.delete()
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
        PlatformAuthenticationService.toggle_platform_key_status(
            platform_key=instance, action=action, user=request.user
        )
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

        organization: Organization = connection.tenant

        PlatformAuthHelper.validate_token_count(organization=organization)

        platform_key = PlatformAuthenticationService.generate_platform_key(
            is_active=is_active, key_name=key_name, user=request.user
        )
        serialized_data = self.serializer_class(platform_key).data
        return Response(
            status=status.HTTP_201_CREATED,
            data=serialized_data,
        )
