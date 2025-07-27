"""Internal API Serializers
Base serializers for internal service APIs.
"""

from rest_framework import serializers


class BaseInternalAPISerializer(serializers.Serializer):
    """Base serializer for internal API responses.
    Provides common fields and validation patterns.
    """

    def validate(self, data):
        """Base validation for internal API requests."""
        # Add any common validation logic here
        return super().validate(data)


class APIResponseSerializer(serializers.Serializer):
    """Standard API response serializer."""

    status = serializers.CharField(max_length=20)
    message = serializers.CharField(max_length=500, required=False)
    data = serializers.DictField(required=False)
    errors = serializers.DictField(required=False)
    timestamp = serializers.DateTimeField(required=False)


class HealthCheckSerializer(serializers.Serializer):
    """Health check response serializer."""

    status = serializers.CharField(max_length=20)
    service = serializers.CharField(max_length=50)
    version = serializers.CharField(max_length=20)
    authenticated = serializers.BooleanField()
    organization_id = serializers.CharField(
        max_length=100, required=False, allow_null=True
    )
    timestamp = serializers.CharField(max_length=100, required=False, allow_null=True)


class ErrorResponseSerializer(serializers.Serializer):
    """Error response serializer."""

    status = serializers.CharField(max_length=20, default="error")
    message = serializers.CharField(max_length=500)
    error = serializers.CharField(max_length=1000, required=False)
    details = serializers.DictField(required=False)
