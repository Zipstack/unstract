from typing import Any

from account_v2.serializer import UserSerializer
from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import PromptStudioRegistry


class PromptStudioRegistrySerializer(AuditSerializer):
    class Meta:
        model = PromptStudioRegistry
        fields = "__all__"


class PromptStudioRegistryInfoSerializer(AuditSerializer):
    shared_users = UserSerializer(many=True)
    prompt_studio_users = serializers.SerializerMethodField()

    class Meta:
        model = PromptStudioRegistry
        fields = (
            "name",
            "shared_users",
            "shared_to_org",
            "prompt_studio_users",
        )

    def get_prompt_studio_users(self, obj: PromptStudioRegistry) -> Any:
        prompt_studio_users = obj.custom_tool.shared_users
        return UserSerializer(prompt_studio_users, many=True).data


class ExportToolRequestSerializer(serializers.Serializer):
    is_shared_with_org = serializers.BooleanField(default=False)
    user_id = serializers.ListField(child=serializers.IntegerField(), required=False)
    force_export = serializers.BooleanField(default=False)
