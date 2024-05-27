from apps.chat_transcript.models import ChatTranscript
from rest_framework.serializers import (
    CharField,
    ModelSerializer,
    Serializer,
    SerializerMethodField,
)

from backend.serializers import AuditSerializer


class ChatTranscriptListSerializer(ModelSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    role = SerializerMethodField()

    def get_role(self, obj: ChatTranscript) -> str:
        """Retrieves the actual string value of role enum.

        Args:
            obj (ChatTranscript): instance of ChatTranscript

        Returns:
            str: value of role enum
        """
        return str(obj.get_role_display())

    class Meta:
        """_summary_"""

        model = ChatTranscript
        fields = "__all__"


class ChatTranscriptSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = ChatTranscript
        exclude = [
            "role",
            "parent_message",
            "chat_history",
        ]


class ChatTranscriptResponseSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    id = CharField()
