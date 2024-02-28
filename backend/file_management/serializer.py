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
        child=serializers.FileField(), required=True,
        validators=[FileValidator(allowed_extensions=['pdf'],
                                  allowed_mimetypes=['application/pdf'],
                                  min_size=0,
                                  max_size=(10*1024*1024*1024))])
    # FileExtensionValidator(allowed_extensions=['pdf'])
    connector_id = serializers.UUIDField()
    path = serializers.CharField()


class FileUploadIdeSerializer(serializers.Serializer):
    file = serializers.ListField(child=serializers.FileField(), required=True,
        validators=[FileValidator(allowed_extensions=['pdf'],
                                  allowed_mimetypes=['application/pdf'],
                                  min_size=0,
                                  max_size=(10*1024*1024*1024))])


class FileInfoIdeSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()


class FileListRequestIdeSerializer(serializers.Serializer):
    tool_id = serializers.CharField()
