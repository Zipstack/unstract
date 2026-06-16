"""Serializers for pipeline sharing functionality."""

from account_v2.serializer import UserSerializer
from pipeline_v2.models import Pipeline
from rest_framework import serializers
from rest_framework.serializers import SerializerMethodField
from tenant_account_v2.sharing_helpers import serialize_group_refs


class SharedUserListSerializer(serializers.ModelSerializer):
    """Serializer for returning pipeline with shared user + group details."""

    shared_users = SerializerMethodField()
    shared_groups = SerializerMethodField()
    created_by = SerializerMethodField()
    co_owners = SerializerMethodField()
    created_by_email = SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = [
            "id",
            "pipeline_name",
            "shared_users",
            "co_owners",
            "shared_to_org",
            "shared_groups",
            "created_by",
            "created_by_email",
        ]

    def get_shared_users(self, obj):
        """Get list of shared users with their details."""
        return UserSerializer(
            obj.shared_users.filter(is_service_account=False), many=True
        ).data

    def get_co_owners(self, obj):
        """Get list of co-owners with their details."""
        return [{"id": u.id, "email": u.email} for u in obj.co_owners.all()]

    def get_shared_groups(self, obj):
        return serialize_group_refs(obj)

    def get_created_by(self, obj):
        """Get the creator's username."""
        return obj.created_by.username if obj.created_by else None

    def get_created_by_email(self, obj):
        """Get the creator's email."""
        return obj.created_by.email if obj.created_by else None
