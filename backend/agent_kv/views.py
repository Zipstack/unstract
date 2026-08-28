import uuid

from global_api_deployment_key.permissions import IsOrganizationAdmin
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from agent_kv.models import AgentKVKey
from agent_kv.serializers import AgentKVKeySerializer, AgentKVKeyWriteSerializer


class AgentKVKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get_queryset(self):
        # No explicit org filter here — the global ``OrganizationFilterBackend``
        # (in DEFAULT_FILTER_BACKENDS) scopes every DRF operation by the
        # current org's ``organization`` FK on this model.
        return AgentKVKey.objects.all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AgentKVKeyWriteSerializer
        return AgentKVKeySerializer

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        key_obj = self.get_object()
        key_obj.key = uuid.uuid4()
        key_obj.save(update_fields=["key", "modified_at"])
        return Response(AgentKVKeySerializer(key_obj).data)
