import uuid

from api_v2.models import APIDeployment
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
        return GlobalApiDeploymentKey.objects.filter(
            organization=UserContext.get_organization(),
        ).prefetch_related("api_deployments")

    def get_serializer_class(self):
        if self.action == "list":
            return GlobalApiDeploymentKeyListSerializer
        if self.action == "create":
            return GlobalApiDeploymentKeyCreateSerializer
        if self.action == "partial_update":
            return GlobalApiDeploymentKeyUpdateSerializer
        return GlobalApiDeploymentKeyListSerializer

    def create(self, request, *args, **kwargs):
        serializer = GlobalApiDeploymentKeyCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GlobalApiDeploymentKeyListSerializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GlobalApiDeploymentKeyUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_instance = serializer.save()
        response_serializer = GlobalApiDeploymentKeyListSerializer(updated_instance)
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
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data)

    @action(detail=False, methods=["get"])
    def deployments(self, request):
        """List all API deployments in the org for admins to assign to keys."""
        organization = UserContext.get_organization()
        deployments = APIDeployment.objects.filter(organization=organization)
        serializer = ApiDeploymentMinimalSerializer(deployments, many=True)
        return Response(serializer.data)
