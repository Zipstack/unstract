import uuid

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.user_context import UserContext

from platform_api.models import PlatformApiKey
from platform_api.permissions import IsOrganizationAdmin
from platform_api.serializers import (
    PlatformApiKeyCreateSerializer,
    PlatformApiKeyDetailSerializer,
    PlatformApiKeyListSerializer,
    PlatformApiKeyUpdateSerializer,
)
from platform_api.services import create_api_user_for_key


class PlatformApiKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

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

        response_serializer = PlatformApiKeyDetailSerializer(platform_api_key)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = PlatformApiKeyDetailSerializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        serializer = PlatformApiKeyUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_instance = serializer.save()

        response_serializer = PlatformApiKeyListSerializer(updated_instance)
        return Response(response_serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def rotate(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.key = uuid.uuid4()
        instance.modified_by = request.user
        instance.save(update_fields=["key", "modified_by"])

        response_serializer = PlatformApiKeyDetailSerializer(instance)
        return Response(response_serializer.data)
