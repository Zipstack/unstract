"""Serializers for pipeline sharing functionality."""

from pipeline_v2.models import Pipeline
from rest_framework import serializers
from rest_framework.serializers import SerializerMethodField


class SharedUserListSerializer(serializers.ModelSerializer):
    """Serializer for returning pipeline with shared user details."""

    shared_users = SerializerMethodField()
    co_owners = SerializerMethodField()
    created_by = SerializerMethodField()
    created_by_email = SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = [
            "id",
            "pipeline_name",
            "shared_users",
            "co_owners",
            "shared_to_org",
            "created_by",
            "created_by_email",
        ]

    def get_shared_users(self, obj):
        """Get list of shared users with their details."""
        return [{"id": u.id, "email": u.email} for u in obj.shared_users.all()]

    def get_co_owners(self, obj):
        """Get list of co-owners with their details."""
        return [{"id": u.id, "email": u.email} for u in obj.co_owners.all()]

    def get_created_by(self, obj):
        """Get the creator's username."""
        return obj.created_by.username if obj.created_by else None

    def get_created_by_email(self, obj):
        """Get the creator's email."""
        return obj.created_by.email if obj.created_by else None
