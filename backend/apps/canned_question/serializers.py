# serializers.py
from apps.canned_question.models import CannedQuestion
from rest_framework.serializers import CharField, ModelSerializer, Serializer
from backend.serializers import AuditSerializer


class CannedQuestionListSerializer(ModelSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = CannedQuestion
        fields = "__all__"


class CannedQuestionSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = CannedQuestion
        fields = "__all__"


class CannedQuestionResponseSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    id = CharField()
