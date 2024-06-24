from file_management.constants import FileInformationKey
from rest_framework import serializers
from utils.FileValidator import FileValidator

from .models import SPSDocument


class SPSDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPSDocument
        fields = "__all__"


class SPSFileUploadSerializer(serializers.Serializer):
    sps_project_id = serializers.CharField()
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


class SPSFileInfoSerializer(serializers.Serializer):
    sps_project_id = serializers.CharField()
    document_id = serializers.CharField()
    view_type = serializers.CharField(required=False)
