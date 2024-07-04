from account.models import User
from account.serializer import UserSerializer
from pluggable_apps.apps.app_deployment.models import AppDeployment, IndexedDocuments
from rest_framework import serializers
from rest_framework.serializers import CharField

from backend.serializers import AuditSerializer


class AppDeploymentListSerializer(AuditSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    workflow_name = CharField(source="workflow.workflow_name", read_only=True)

    class Meta:
        """_summary_"""

        model = AppDeployment
        fields = [
            "id",
            "workflow",
            "workflow_name",
            "app_display_name",
            "description",
            "is_active",
            "app_name",
            "created_by",
        ]


class AppDeploymentSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    shared_users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True, many=True
    )

    class Meta:
        """_summary_"""

        model = AppDeployment
        fields = "__all__"


class SharedUserListSerializer(serializers.ModelSerializer):
    """Used for listing users of Custom tool."""

    created_by = UserSerializer()
    shared_users = UserSerializer(many=True)

    class Meta:
        model = AppDeployment()
        fields = (
            "app_name",
            "created_by",
            "shared_users",
        )


class IndexedDocumentsSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = IndexedDocuments
        fields = "__all__"


class DocumentIDSerializer(serializers.Serializer):
    doc_id = serializers.CharField(max_length=256)
    file_name = serializers.CharField(max_length=256)


class FileUploadResponseSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=256)
    doc_ids = DocumentIDSerializer(
        many=True,
    )
