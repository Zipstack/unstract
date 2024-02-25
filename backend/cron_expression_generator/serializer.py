import logging

from backend.constants import FieldLengthConstants as FLC
from rest_framework import serializers

logger = logging.getLogger(__name__)


class CronGenerateSerializer(serializers.Serializer):
    frequency = serializers.CharField(max_length=FLC.CRON_LENGTH, required=False)
    cron_string = serializers.CharField(max_length=FLC.CRON_LENGTH, required=False)
    summary = serializers.CharField(max_length=FLC.CRON_LENGTH, required=False)
