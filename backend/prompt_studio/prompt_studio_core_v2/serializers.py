import logging
from typing import Any

from account_v2.serializer import UserSerializer
from adapter_processor_v2.models import AdapterInstance
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from tenant_account_v2.sharing_helpers import (
    serialize_group_refs,
    serialize_owner_refs,
)
from utils.FileValidator import FileValidator
from utils.input_sanitizer import validate_name_field, validate_no_html_tags
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin

from backend.serializers import AuditSerializer
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.constants import ToolStudioKeys as TSKeys
from prompt_studio.prompt_studio_core_v2.exceptions import DefaultProfileError
from prompt_studio.prompt_studio_output_manager_v2.output_manager_util import (
    OutputManagerUtils,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from prompt_studio.prompt_studio_v2.serializers import ToolStudioPromptSerializer
from unstract.sdk1.adapters.enums import AdapterTypes

from .models import CustomTool

logger = logging.getLogger(__name__)

try:
    from plugins.processor.file_converter.constants import (
        ExtentedFileInformationKey as FileKey,
    )
except ImportError:
    from file_management.constants import FileInformationKey as FileKey


class CustomToolListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the list endpoint.

    Avoids the O(tools x prompts) queries that CustomToolSerializer.to_representation
    causes by skipping profile lookups, prompt fetching, and coverage calculation.
    """

    created_by_email = serializers.SerializerMethodField()
    prompt_count = serializers.SerializerMethodField()
    modified_at = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    co_owners_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomTool
        fields = [
            "tool_id",
            "tool_name",
            "description",
            "author",
            "created_by",
            "created_at",
            "modified_at",
            "shared_to_org",
            "icon",
            "created_by_email",
            "prompt_count",
            "is_owner",
            "co_owners_count",
        ]

    def get_created_by_email(self, instance):
        return instance.created_by.email if instance.created_by else ""

    def get_modified_at(self, instance):
        """Latest of the tool's own modified_at and its prompts' — prompt
        edits never touch the CustomTool row (UN-3741).
        """
        last_prompt_modified = getattr(instance, "_last_prompt_modified", None)
        if last_prompt_modified and last_prompt_modified > instance.modified_at:
            return last_prompt_modified
        return instance.modified_at

    def get_is_owner(self, instance) -> bool:
        request = self.context.get("request")
        return instance.is_owner(request.user) if request else False

    def get_co_owners_count(self, instance) -> int:
        return instance.co_owners_count()

    def get_prompt_count(self, instance):
        if hasattr(instance, "_prompt_count"):
            return instance._prompt_count or 0
        # Fallback triggers a per-instance query if annotation is missing
        logger.warning(
            "CustomToolListSerializer used without _prompt_count annotation "
            "for tool %s — falling back to per-instance query",
            instance.tool_id,
        )
        return instance.mapped_prompt.count()


class CustomToolSerializer(IntegrityErrorMixin, AuditSerializer):
    # Share mutations go through ``POST /prompt-studio/{id}/share/``; the
    # groups axis is read-only here (UN-2977 plan §B). Direct viewers live in
    # the membership table (UN-2202) and surface via the share-modal serializer.
    shared_groups = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = CustomTool
        fields = "__all__"
        extra_kwargs = {
            "shared_to_org": {"read_only": True},
        }

    unique_error_message_map: dict[str, dict[str, str]] = {
        "unique_tool_name": {
            "field": "tool_name",
            "message": (
                "This tool name is already in use. Please select a different name."
            ),
        }
    }

    def validate_tool_name(self, value: str) -> str:
        return validate_name_field(value, field_name="Tool name")

    def validate_description(self, value: str) -> str:
        if value is None:
            return value
        return validate_no_html_tags(value, field_name="Description")

    def validate_summarize_llm_adapter(self, value):
        """Validate that the adapter type is LLM and is accessible to the user."""
        if value is None:
            return value

        # Check if user has access to this adapter
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            try:
                adapter = AdapterInstance.objects.for_user(request.user).get(id=value.id)
                # Validate that the adapter type is LLM
                if adapter.adapter_type != AdapterTypes.LLM.value:
                    raise ValidationError(
                        "Only LLM adapters are allowed for summarization"
                    )
            except AdapterInstance.DoesNotExist:
                raise ValidationError("Selected LLM adapter not found or not accessible")

        return value

    def update(self, instance, validated_data):
        """Custom update method to handle profile clearing when adapter is set."""
        instance = super().update(instance, validated_data)
        if validated_data.get("summarize_llm_adapter"):
            # Clear any existing deprecated profile-based summarize setting
            ProfileManager.objects.filter(prompt_studio_tool=instance).update(
                is_summarize_llm=False
            )
            return instance

        return instance

    def to_representation(self, instance):  # type: ignore
        data = super().to_representation(instance)
        default_profile = None

        # Check new adapter-based approach first
        if instance.summarize_llm_adapter:
            data[TSKeys.SUMMARIZE_LLM_ADAPTER] = instance.summarize_llm_adapter.id

        # Check legacy profile-based approach
        try:
            summarize_profile = ProfileManager.objects.get(
                prompt_studio_tool=instance, is_summarize_llm=True
            )
            if summarize_profile.llm:
                data[TSKeys.SUMMARIZE_LLM_PROFILE] = summarize_profile.profile_id
        except ObjectDoesNotExist:
            pass

        # Fetch default LLM profile
        try:
            default_profile = ProfileManager.get_default_llm_profile(instance)
            data[TSKeys.DEFAULT_PROFILE] = default_profile.profile_id
        except DefaultProfileError:
            # To make it compatible with older projects error suppressed with warning.
            logger.warning(
                "Default LLM profile doesn't exist for prompt tool %s",
                str(instance.tool_id),
            )

        # Fetch prompt instances
        prompt_instances: ToolStudioPrompt = ToolStudioPrompt.objects.filter(
            tool_id=data.get(TSKeys.TOOL_ID)
        ).order_by("sequence_number")

        data["created_by_email"] = (
            instance.created_by.email if instance.created_by else ""
        )

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

        return data


class PromptStudioIndexSerializer(serializers.Serializer):
    document_id = serializers.CharField()


class PromptStudioResponseSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()
    id = serializers.CharField()


class SharedUserListSerializer(serializers.ModelSerializer):
    """Used for listing users + groups of Custom tool."""

    created_by = UserSerializer()
    shared_users = serializers.SerializerMethodField()
    shared_groups = serializers.SerializerMethodField()
    co_owners = serializers.SerializerMethodField()

    class Meta:
        model = CustomTool
        fields = (
            "tool_id",
            "tool_name",
            "created_by",
            "shared_users",
            "shared_to_org",
            "shared_groups",
            "co_owners",
        )

    def get_shared_users(self, obj):
        viewers = [u for u in obj.viewers() if not u.is_service_account]
        return UserSerializer(viewers, many=True).data

    def get_shared_groups(self, obj):
        return serialize_group_refs(obj)

    def get_co_owners(self, obj):
        return serialize_owner_refs(obj)


class FileInfoIdeSerializer(serializers.Serializer):
    document_id = serializers.CharField()
    view_type = serializers.CharField(required=False)


class FileUploadIdeSerializer(serializers.Serializer):
    file = serializers.ListField(
        child=serializers.FileField(),
        required=True,
        validators=[
            FileValidator(
                allowed_extensions=FileKey.FILE_UPLOAD_ALLOWED_EXT,
                allowed_mimetypes=FileKey.FILE_UPLOAD_ALLOWED_MIME,
                min_size=0,
                max_size=FileKey.FILE_UPLOAD_MAX_SIZE,
            )
        ],
    )


class SyncPromptsSerializer(serializers.Serializer):
    data = serializers.DictField(required=True)
    create_copy = serializers.BooleanField(default=False)

    def validate_data(self, value):
        required_keys = {"prompts"}
        if not required_keys.issubset(value.keys()):
            raise serializers.ValidationError(
                f"Export JSON must contain keys: {required_keys}"
            )
        return value
