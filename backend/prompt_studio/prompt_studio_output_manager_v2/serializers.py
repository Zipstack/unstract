import json
import logging

from usage_v2.helper import UsageHelper

from backend.serializers import AuditSerializer

from .models import PromptStudioOutputManager

logger = logging.getLogger(__name__)


class PromptStudioOutputSerializer(AuditSerializer):
    class Meta:
        model = PromptStudioOutputManager
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            token_usage = UsageHelper.get_aggregated_token_count(instance.run_id)
        except Exception as e:
            logger.error(
                "Error occured while fetching token usage for run_id"
                f"{instance.run_id}: {e}"
            )
            token_usage = {}
        data["token_usage"] = token_usage
        # Convert string to list
        try:
            data["context"] = json.loads(data["context"])
        except json.JSONDecodeError:
            # Convert the old value of data["context"] to a list
            data["context"] = [data["context"]]
        return data
