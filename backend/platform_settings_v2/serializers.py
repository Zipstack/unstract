from account_v2.models import PlatformKey
from backend.serializers import AuditSerializer
from rest_framework import serializers


class PlatformKeySerializer(AuditSerializer):
    class Meta:
        model = PlatformKey
        fields = "__all__"


class PlatformKeyGenerateSerializer(serializers.Serializer):
    # Adjust these fields based on your actual serializer
    is_active = serializers.BooleanField()

    key_name = serializers.CharField()


class PlatformKeyIDSerializer(serializers.Serializer):
    id = serializers.CharField()
    key_name = serializers.CharField()
    key = serializers.CharField()
    is_active = serializers.BooleanField()
