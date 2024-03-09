import logging
from typing import Any

from backend.serializers import AuditSerializer
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio.serializers import ToolStudioPromptSerializer
from prompt_studio.prompt_studio_core.constants import ToolStudioKeys as TSKeys
from rest_framework import serializers

from .models import CustomTool

logger = logging.getLogger(__name__)


class CustomToolSerializer(AuditSerializer):
    class Meta:
        model = CustomTool
        fields = "__all__"

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        try:
            prompt_instance: ToolStudioPrompt = ToolStudioPrompt.objects.filter(
                tool_id=data.get(TSKeys.TOOL_ID)
            ).order_by("sequence_number")
            data[TSKeys.PROMPTS] = []
            output: list[Any] = []
            # Appending prompt instances of the tool for FE Processing
            if prompt_instance.count() != 0:
                for prompt in prompt_instance:
                    prompt_serializer = ToolStudioPromptSerializer(prompt)
                    output.append(prompt_serializer.data)
                data[TSKeys.PROMPTS] = output
        except Exception as e:
            logger.error(f"Error occured while appending prompts {e}")
            return data
        return data


class PromptStudioIndexSerializer(serializers.Serializer):
    prompt_document_id = serializers.CharField()
    tool_id = serializers.CharField()


class PromptStudioResponseSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()
    id = serializers.CharField()
