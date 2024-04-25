import logging

from backend.serializers import AuditSerializer

from .models import TagManager

logger = logging.getLogger(__name__)


class PromptTagSerializer(AuditSerializer):
    """_summary_
    """

    class Meta:
        model = TagManager
        fields = "__all__"
