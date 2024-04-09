import logging
from typing import Any

from account.models import User
from account.serializer import UserSerializer
from django.core.exceptions import ObjectDoesNotExist
from file_management.constants import FileInformationKey
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio.serializers import ToolStudioPromptSerializer
from prompt_studio.prompt_studio_core.constants import ToolStudioKeys as TSKeys
from prompt_studio.prompt_studio_core.exceptions import DefaultProfileError
from rest_framework import serializers
from utils.FileValidator import FileValidator

from backend.serializers import AuditSerializer

from .models import CustomTool

logger = logging.getLogger(__name__)


class CustomToolSerializer(AuditSerializer):
    shared_users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True, many=True
    )

    class Meta:
        model = CustomTool
        fields = "__all__"

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        try:
            profile_manager = ProfileManager.objects.get(
                prompt_studio_tool=instance, is_summarize_llm=True
            )
            data[TSKeys.SUMMARIZE_LLM_PROFILE] = profile_manager.profile_id
        except ObjectDoesNotExist:
            logger.info(
                "Summarize LLM profile doesnt exist for prompt tool %s",
                str(instance.tool_id),
            )
        try:
            profile_manager = ProfileManager.get_default_llm_profile(instance)
            data[TSKeys.DEFAULT_PROFILE] = profile_manager.profile_id
        except DefaultProfileError:
            logger.info(
                "Default LLM profile doesnt exist for prompt tool %s",
                str(instance.tool_id),
            )
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

        data["created_by_email"] = instance.created_by.email

        return data


class PromptStudioIndexSerializer(serializers.Serializer):
    document_id = serializers.CharField()


class PromptStudioResponseSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()
    id = serializers.CharField()


class SharedUserListSerializer(serializers.ModelSerializer):
    """Used for listing users of Custom tool."""

    created_by = UserSerializer()
    shared_users = UserSerializer(many=True)

    class Meta:
        model = CustomTool
        fields = (
            "tool_id",
            "tool_name",
            "created_by",
            "shared_users",
        )


class FileInfoIdeSerializer(serializers.Serializer):
    document_id = serializers.CharField()
    view_type = serializers.CharField(required=False)


class FileUploadIdeSerializer(serializers.Serializer):
    file = serializers.ListField(
        child=serializers.FileField(),
        required=True,
        validators=[
            FileValidator(
                allowed_extensions=FileInformationKey.FILE_UPLOAD_ALLOWED_EXT,
                allowed_mimetypes=FileInformationKey.FILE_UPLOAD_ALLOWED_MIME,
                min_size=0,
                max_size=FileInformationKey.FILE_UPLOAD_MAX_SIZE,
            )
        ],
    )
