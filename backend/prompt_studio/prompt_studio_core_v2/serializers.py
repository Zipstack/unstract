import logging
from typing import Any

from account_v2.models import User
from account_v2.serializer import UserSerializer
from django.core.exceptions import ObjectDoesNotExist
from file_management.constants import FileInformationKey
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.constants import ToolStudioKeys as TSKeys
from prompt_studio.prompt_studio_core_v2.exceptions import DefaultProfileError
from prompt_studio.prompt_studio_output_manager_v2.output_manager_util import (
    OutputManagerUtils,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from prompt_studio.prompt_studio_v2.serializers import ToolStudioPromptSerializer
from rest_framework import serializers
from utils.FileValidator import FileValidator
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin

from backend.serializers import AuditSerializer

from .models import CustomTool

logger = logging.getLogger(__name__)


class CustomToolSerializer(IntegrityErrorMixin, AuditSerializer):
    shared_users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True, many=True
    )

    class Meta:
        model = CustomTool
        fields = "__all__"

    unique_error_message_map: dict[str, dict[str, str]] = {
        "unique_tool_name": {
            "field": "tool_name",
            "message": (
                "This tool name is already in use. Please select a different name."
            ),
        }
    }

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        default_profile = None

        # Fetch summarize LLM profile
        try:
            summarize_profile = ProfileManager.objects.get(
                prompt_studio_tool=instance, is_summarize_llm=True
            )
            data[TSKeys.SUMMARIZE_LLM_PROFILE] = summarize_profile.profile_id
        except ObjectDoesNotExist:
            logger.info(
                "Summarize LLM profile doesn't exist for prompt tool %s",
                str(instance.tool_id),
            )

        # Fetch default LLM profile
        try:
            default_profile = ProfileManager.get_default_llm_profile(instance)
            data[TSKeys.DEFAULT_PROFILE] = default_profile.profile_id
        except DefaultProfileError:
            logger.warning(
                "Default LLM profile doesn't exist for prompt tool %s",
                str(instance.tool_id),
            )

        # Fetch prompt instances
        prompt_instances: ToolStudioPrompt = ToolStudioPrompt.objects.filter(
            tool_id=data.get(TSKeys.TOOL_ID)
        ).order_by("sequence_number")

        if not prompt_instances.exists():
            data[TSKeys.PROMPTS] = []
            return data

        # Process prompt instances
        output: list[Any] = []
        for prompt in prompt_instances:
            prompt_serializer = ToolStudioPromptSerializer(prompt)
            serialized_data = prompt_serializer.data

            # Determine coverage
            coverage: list[Any] = []
            profile_manager_id = prompt.profile_manager
            if default_profile and instance.single_pass_extraction_mode:
                profile_manager_id = default_profile.profile_id

            if profile_manager_id:
                coverage = OutputManagerUtils.get_coverage(
                    data.get(TSKeys.TOOL_ID),
                    profile_manager_id,
                    prompt.prompt_id,
                    instance.single_pass_extraction_mode,
                )
            else:
                logger.info(
                    "Skipping coverage calculation for prompt %s "
                    "due to missing profile ID",
                    str(prompt.prompt_key),
                )

            # Add coverage to serialized data
            serialized_data["coverage"] = coverage
            output.append(serialized_data)

        data[TSKeys.PROMPTS] = output
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
