from typing import Any

from account_v2.serializer import UserSerializer
from backend.serializers import AuditSerializer
from rest_framework import serializers

from .models import PromptStudioRegistry


class PromptStudioRegistrySerializer(AuditSerializer):
    class Meta:
        model = PromptStudioRegistry
        fields = "__all__"


class PromptStudioRegistryInfoSerializer(AuditSerializer):
    shared_users = serializers.SerializerMethodField()
    prompt_studio_users = serializers.SerializerMethodField()

    class Meta:
        model = PromptStudioRegistry
        fields = (
            "name",
            "shared_users",
            "shared_to_org",
            "prompt_studio_users",
        )

    def get_shared_users(self, obj: PromptStudioRegistry) -> Any:
        return UserSerializer(
            obj.shared_users.filter(is_service_account=False), many=True
        ).data

    def get_prompt_studio_users(self, obj: PromptStudioRegistry) -> Any:
        # ``CustomTool.shared_users`` was replaced by polymorphic memberships
        # (UN-2202); read owners + viewers instead. The unique membership
        # constraint (user, content_type, object_id) rules out duplicates.
        tool = obj.custom_tool
        users = [u for u in (*tool.owners(), *tool.viewers()) if not u.is_service_account]
        return UserSerializer(users, many=True).data


class ExportToolRequestSerializer(serializers.Serializer):
    is_shared_with_org = serializers.BooleanField(default=False)
    user_id = serializers.ListField(child=serializers.IntegerField(), required=False)
    force_export = serializers.BooleanField(default=False)
