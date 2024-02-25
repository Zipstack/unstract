from rest_framework import serializers


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
    file = serializers.ListField(child=serializers.FileField(), required=True)
    connector_id = serializers.UUIDField()
    path = serializers.CharField()


class FileUploadIdeSerializer(serializers.Serializer):
    file = serializers.ListField(child=serializers.FileField(), required=True)


class FileInfoIdeSerializer(serializers.Serializer):
    file_name = serializers.CharField()
    tool_id = serializers.CharField()


class FileListRequestIdeSerializer(serializers.Serializer):
    tool_id = serializers.CharField()
