from rest_framework import serializers


class GetUsageSerializer(serializers.Serializer):
    run_id = serializers.CharField(required=True)
