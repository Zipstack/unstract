from typing import Any

from prompt_studio.prompt_version_manager.helper import PromptVersionHelper
from rest_framework import serializers

from backend.serializers import AuditSerializer

from .models import ToolStudioPrompt


class ToolStudioPromptSerializer(AuditSerializer):

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        request = self.context.get("request")
        if request and instance.prompt_type == "PROMPT":
            # Create a new instance from the existing instance
            prompt_instance = ToolStudioPrompt(
                tool_id=instance.tool_id,
                prompt_id=instance.prompt_id,
                prompt_key=instance.prompt_key,
                prompt=instance.prompt,
                enforce_type=instance.enforce_type,
                profile_manager=instance.profile_manager,
            )
            # Iterate over validated_data and set those keys in prompt_instance
            for key, value in validated_data.items():
                setattr(prompt_instance, key, value)
            validated_data["loaded_version"] = PromptVersionHelper.get_prompt_version(
                prompt_instance
            )
        return super().update(instance, validated_data)

    class Meta:
        model = ToolStudioPrompt
        fields = "__all__"
        read_only_fields = ["loaded_version"]


class ToolStudioIndexSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()


class ReorderPromptsSerializer(serializers.Serializer):
    start_sequence_number = serializers.IntegerField(required=True)
    end_sequence_number = serializers.IntegerField(required=True)
    prompt_id = serializers.CharField(required=True)

    def validate(self, data):
        start_sequence_number = data.get("start_sequence_number")
        end_sequence_number = data.get("end_sequence_number")

        if start_sequence_number == end_sequence_number:
            raise serializers.ValidationError(
                "Start and end sequence numbers cannot be the same."
            )

        return data
