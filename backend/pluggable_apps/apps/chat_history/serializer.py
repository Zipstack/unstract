from pluggable_apps.apps.chat_history.models import ChatHistory
from rest_framework.serializers import CharField, ModelSerializer, Serializer

from backend.serializers import AuditSerializer


class ChatHistoryListSerializer(ModelSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = ChatHistory
        fields = "__all__"


class ChatHistorySerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = ChatHistory
        fields = "__all__"


class ChatHistoryRequestSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    label = CharField(
        required=True,
    )
    app_id = CharField(
        required=True,
    )


class ChatHistoryResponseSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    id = CharField()
