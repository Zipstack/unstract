from permissions.permission import IsOwner
from utils.user_context import UserContext


class IsOwnerOrOrganizationMember(IsOwner):
    """Permission that grants access if the user is the owner or belongs to the
    same organization.
    """

    def has_object_permission(self, request, view, obj):
        # Check if the user is the owner via base class logic
        if super().has_object_permission(request, view, obj):
            return True

        # If the object has a 'created_by' field, but the user isn't the owner,
        # deny access
        if obj.created_by:
            return False

        # Support legacy API keys where 'created_by' is None by matching the
        # organization ID. This allows organization members to access API keys as per
        # the existing behavior.
        user_organization = UserContext.get_organization()
        # Check organization ID for associated `api` or `pipeline`
        related_obj = getattr(obj, "api", None) or getattr(obj, "pipeline", None)
        if related_obj and related_obj.organization_id == user_organization.id:
            return True

        return False
