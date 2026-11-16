import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agent_kv.models import AgentKVKey
from agent_kv.permissions import IsOrganizationAdmin
from agent_kv.serializers import (
    AgentKVKeyCreateSerializer,
    AgentKVKeyDetailSerializer,
    AgentKVKeyListSerializer,
    AgentKVKeyUpdateSerializer,
)


class AgentKVKeyViewSet(viewsets.ModelViewSet):
    """Key management for the Agent-KV public API.

    Shaped on ``platform_api.views.PlatformApiKeyViewSet`` because the
    ``ApiKeyManager`` screen in the frontend is shared between them: the table
    reads a masked ``key`` plus ``created_by_email`` from the list, and the
    copy/create/rotate actions read the real value from a single-key response.
    A viewset that returned one serializer for everything would either leak
    every key into the table or leave the copy button with nothing to copy.
    """

    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get_queryset(self):
        # No explicit org filter here — the global ``OrganizationFilterBackend``
        # (in DEFAULT_FILTER_BACKENDS) scopes every DRF operation by the
        # current org's ``organization`` FK on this model.
        return AgentKVKey.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return AgentKVKeyCreateSerializer
        if self.action == "partial_update":
            return AgentKVKeyUpdateSerializer
        if self.action in ("retrieve", "rotate"):
            return AgentKVKeyDetailSerializer
        return AgentKVKeyListSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """Respond with the DETAIL serializer, not the write one (DRF's default).

        ``AgentKVKeyCreateSerializer`` only carries ``name``/``description``,
        so the standard ``CreateModelMixin.create`` would echo that back and
        the admin who just created a key would never see ``id`` or the key
        itself. Both are server-generated, and create is one of the three
        places the plaintext value is ever returned — mirrors
        ``PlatformApiKeyViewSet.create``.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            AgentKVKeyDetailSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        """Answer with the LIST shape so the table can patch its row in place.

        The update serializer carries only the writable fields; echoing it
        would leave the row without ``key``, ``created_at`` or
        ``created_by_email`` until the next refetch.
        """
        instance = self.get_object()
        serializer = AgentKVKeyUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(AgentKVKeyListSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        key_obj = self.get_object()
        key_obj.key = uuid.uuid4()
        key_obj.save(update_fields=["key", "modified_at"])
        return Response(AgentKVKeyDetailSerializer(key_obj).data)
