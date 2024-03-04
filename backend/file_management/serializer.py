from file_management.constants import FileInformationKey
from rest_framework import serializers
from utils.FileValidator import FileValidator


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
                allowed_extensions=FileInformationKey.FILE_UPLOAD_ALLOWED_EXTENSIONS,
                allowed_mimetypes=FileInformationKey.FILE_UPLOAD_ALLOWED_MIMETYPES,
                min_size=0,
                max_size=FileInformationKey.FILE_UPLOAD_MAX_SIZE,
            )  # type: ignore
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
                allowed_extensions=FileInformationKey.FILE_UPLOAD_ALLOWED_EXTENSIONS,
                allowed_mimetypes=FileInformationKey.FILE_UPLOAD_ALLOWED_MIMETYPES,
                min_size=0,
                max_size=FileInformationKey.FILE_UPLOAD_MAX_SIZE,
            )  # type: ignore
        ],
    )


class FileInfoIdeSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()


class FileListRequestIdeSerializer(serializers.Serializer):
    tool_id = serializers.CharField()
