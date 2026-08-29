import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from agent_kv.models import AgentKVKey
from agent_kv.permissions import IsOrganizationAdmin
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

    def create(self, request, *args, **kwargs):
        """Respond with the read serializer, not the write one (DRF's default).

        ``AgentKVKeyWriteSerializer`` (used to validate the request, per
        ``get_serializer_class``) only carries ``name``/``description``/
        ``is_active`` -- the standard ``CreateModelMixin.create`` would echo
        that same serializer back, meaning the caller who just created a key
        would never see ``id`` or the raw ``key`` value itself. Both are
        server-generated and this is the only response that will ever carry
        the plaintext key (list/retrieve return it too today, but rotate is
        the only other place a caller can *see* a fresh one) -- mirrors
        ``GlobalApiDeploymentKeyViewSet.create``.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_serializer = AgentKVKeySerializer(serializer.instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        key_obj = self.get_object()
        key_obj.key = uuid.uuid4()
        key_obj.save(update_fields=["key", "modified_at"])
        return Response(AgentKVKeySerializer(key_obj).data)
