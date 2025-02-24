from rest_framework import serializers


class DateRangeSerializer(serializers.Serializer):
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
