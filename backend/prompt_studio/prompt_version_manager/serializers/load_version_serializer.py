import re

from rest_framework import serializers


class LoadVersionSerializer(serializers.Serializer):
    prompt_version = serializers.CharField(max_length=10)

    def validate_prompt_version(self, value):
        if not re.match(r"^v\d+$", value):
            raise serializers.ValidationError(
                "prompt_version must start with 'v' followed by numbers only."
            )
        if len(value) > 10:
            raise serializers.ValidationError(
                "prompt_version must not exceed 10 characters."
            )
        return value
