from typing import Any

from rest_framework.serializers import ModelSerializer

from backend.constants import RequestKey


class AuditSerializer(ModelSerializer):
    def create(self, validated_data: dict[str, Any]) -> Any:
        request = self.context.get(RequestKey.REQUEST)
        if request:
            validated_data[RequestKey.CREATED_BY] = request.user
            validated_data[RequestKey.MODIFIED_BY] = request.user
        instance = super().create(validated_data)

        # Auto-add key owner as co-owner for resources created via API key
        if request and hasattr(request, "platform_api_key"):
            platform_api_key = request.platform_api_key
            if hasattr(instance, "shared_users") and platform_api_key.created_by:
                instance.shared_users.add(platform_api_key.created_by)

        return instance

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        if self.context.get(RequestKey.REQUEST):
            validated_data[RequestKey.MODIFIED_BY] = self.context.get(
                RequestKey.REQUEST
            ).user
        return super().update(instance, validated_data)
