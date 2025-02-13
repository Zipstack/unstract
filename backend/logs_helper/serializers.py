from rest_framework import serializers


class StoreLogMessagesSerializer(serializers.Serializer):
    log = serializers.CharField()
