from django.shortcuts import get_object_or_404
from permissions.permission import _is_resource_owner, _is_resource_viewer
from rest_framework.permissions import BasePermission
from tenant_account_v2.organization_member_service import OrganizationMemberService

from workflow_manager.workflow_v2.models.workflow import Workflow


class IsWorkflowOwnerOrShared(BasePermission):
    """Permission class to check if user has access to a workflow.

    Checks:
    1. User owns the workflow (OWNER membership; ``created_by`` is audit-only).
    2. User is a direct viewer (VIEWER membership).
    3. Workflow is shared to user's organization (shared_to_org).

    Caches the workflow on request object to avoid duplicate fetching.
    """

    message = "You do not have permission to access this workflow"

    def has_permission(self, request, view):
        workflow_id = view.kwargs.get("workflow_id")

        if not workflow_id:
            return False

        # Cache workflow on request to avoid re-fetching in get_queryset
        if not hasattr(request, "_workflow_cache"):
            request._workflow_cache = get_object_or_404(
                Workflow.objects.select_related(
                    "created_by", "organization"
                ).prefetch_related("memberships__user"),
                id=workflow_id,
            )

        workflow = request._workflow_cache
        user = request.user

        has_access = (
            _is_resource_owner(user, workflow)
            or _is_resource_viewer(user, workflow)
            or (workflow.shared_to_org and workflow.organization == user.organization)
            or OrganizationMemberService.is_user_organization_admin(user)
        )

        return has_access
