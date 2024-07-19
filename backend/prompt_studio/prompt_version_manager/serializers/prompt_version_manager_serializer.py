import logging

from prompt_studio.prompt_profile_manager.serializers import ProfileManagerSerializer
from prompt_studio.prompt_version_manager.models import PromptVersionManager

from backend.serializers import AuditSerializer

logger = logging.getLogger(__name__)


class PromptVersionManagerSerializer(AuditSerializer):
    profile_manager = ProfileManagerSerializer(
        fields=("profile_id", "llm", "embedding_model", "vector_store", "x2text")
    )

    class Meta:
        model = PromptVersionManager
        fields = (
            "prompt_version_manager_id",
            "version",
            "prompt_key",
            "prompt",
            "enforce_type",
            "profile_manager",
        )
