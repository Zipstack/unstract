"""Account Internal API Serializers
Handles serialization for organization context related endpoints.
"""

from rest_framework import serializers


class OrganizationContextSerializer(serializers.Serializer):
    """Serializer for organization context information."""

    organization_id = serializers.CharField()
    organization_name = serializers.CharField()
    organization_slug = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.CharField(required=False, allow_blank=True)
    settings = serializers.DictField(required=False)
