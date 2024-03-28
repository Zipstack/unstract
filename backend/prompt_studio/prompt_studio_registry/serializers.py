from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import PromptStudioRegistry


class PromptStudioRegistrySerializer(AuditSerializer):
    class Meta:
        model = PromptStudioRegistry
        fields = "__all__"


class ExportToolRequestSerializer(serializers.Serializer):
    prompt_registry_id = serializers.UUIDField(required=True)
