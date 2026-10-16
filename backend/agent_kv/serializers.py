from rest_framework import serializers

from agent_kv.models import AgentKVKey


class AgentKVKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentKVKey
        fields = ["id", "name", "description", "key", "is_active", "created_at"]


class AgentKVKeyWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentKVKey
        fields = ["name", "description", "is_active"]
