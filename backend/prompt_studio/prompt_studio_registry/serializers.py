from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import PromptStudioRegistry


class PromptStudioRegistrySerializer(AuditSerializer):
    class Meta:
        model = PromptStudioRegistry
        fields = "__all__"


class ExportToolRequestSerializer(serializers.Serializer):
    is_shared_with_org = serializers.BooleanField(default=False)
    user_id = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
