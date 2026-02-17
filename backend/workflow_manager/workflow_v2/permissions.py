from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission

from workflow_manager.workflow_v2.models.workflow import Workflow


class IsWorkflowOwnerOrShared(BasePermission):
    """Permission class to check if user has access to a workflow.

    Checks:
    1. User is the workflow owner (created_by)
    2. User has shared access (in shared_users)
    3. Workflow is shared to user's organization (shared_to_org)

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
                ).prefetch_related("shared_users", "co_owners"),
                id=workflow_id,
            )

        workflow = request._workflow_cache
        user = request.user

        # Check access: owner OR co-owner OR shared user OR shared to org
        has_access = (
            workflow.created_by == user
            or user in workflow.co_owners.all()
            or user in workflow.shared_users.all()
            or (workflow.shared_to_org and workflow.organization == user.organization)
        )

        return has_access
