from typing import Any

from rest_framework import serializers

from .models import Prompt


class PromptSerializer(serializers.ModelSerializer):
    def create(self, validated_data: dict[str, Any]) -> Any:
        validated_data["created_by"] = self.context.get("request")._user
        return super().create(validated_data)

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        validated_data["modified_by"] = self.context.get("request")._user
        return super().update(instance, validated_data)

    class Meta:
        model = Prompt
        fields = "__all__"
