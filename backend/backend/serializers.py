from typing import Any

from rest_framework.serializers import ModelSerializer

from backend.constants import RequestKey


class AuditSerializer(ModelSerializer):
    def create(self, validated_data: dict[str, Any]) -> Any:
        if self.context.get(RequestKey.REQUEST):
            validated_data[RequestKey.CREATED_BY] = self.context.get(
                RequestKey.REQUEST
            ).user
            validated_data[RequestKey.MODIFIED_BY] = self.context.get(
                RequestKey.REQUEST
            ).user
        return super().create(validated_data)

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        if self.context.get(RequestKey.REQUEST):
            validated_data[RequestKey.MODIFIED_BY] = self.context.get(
                RequestKey.REQUEST
            ).user
        return super().update(instance, validated_data)
