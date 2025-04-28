from rest_framework import serializers
from utils.FileValidator import FileValidator

from file_management.constants import FileInformationKey


class FileInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    type = serializers.CharField()
    modified_at = serializers.CharField()
    content_type = serializers.CharField()
    size = serializers.FloatField()


class FileListRequestSerializer(serializers.Serializer):
    connector_id = serializers.UUIDField()
    path = serializers.CharField()


class FileUploadSerializer(serializers.Serializer):
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
    # FileExtensionValidator(allowed_extensions=['pdf'])
    connector_id = serializers.UUIDField()
    path = serializers.CharField()


class FileUploadIdeSerializer(serializers.Serializer):
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


class FileInfoIdeSerializer(serializers.Serializer):
    document_id = serializers.CharField()
    tool_id = serializers.CharField()
    view_type = serializers.CharField(required=False)


class FileListRequestIdeSerializer(serializers.Serializer):
    tool_id = serializers.CharField()
