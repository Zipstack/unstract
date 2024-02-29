from rest_framework import serializers


class FileListRequestSerializer(serializers.Serializer):
    app_id = serializers.UUIDField(required=True)
    dir_only = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(default=100)


class ViewFileRequestSerializer(serializers.Serializer):
    app_id = serializers.UUIDField(required=True)
    file_name = serializers.CharField(required=True)
