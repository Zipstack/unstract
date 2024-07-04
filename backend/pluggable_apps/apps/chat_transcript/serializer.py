from pluggable_apps.apps.chat_transcript.models import ChatTranscript
from rest_framework import serializers
from rest_framework.serializers import CharField, ModelSerializer, Serializer, UUIDField

from backend.serializers import AuditSerializer


class ChatTranscriptListSerializer(ModelSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = ChatTranscript
        fields = "__all__"


class ChatTranscriptSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    session_id = serializers.CharField(required=False)

    class Meta:
        """_summary_"""

        model = ChatTranscript
        fields = "__all__"


class ChatTranscripRequestSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    message = CharField(
        required=True,
    )
    chat_history_id = UUIDField(
        required=True,
    )
