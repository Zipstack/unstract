import logging
from typing import Any

from adapter_processor_v2.models import AdapterInstance
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.views import APIView
from tenant_account_v2.organization_member_service import OrganizationMemberService
from utils.user_context import UserContext

logger = logging.getLogger(__name__)

_REQUEST_ADMIN_CACHE_ATTR = "_cached_is_organization_admin"


def _is_service_account(request: Request) -> bool:
    """Allow service accounts through regardless of HTTP method.

    The authentication middleware has already checked the key's permission
    tier against the request method (``ApiKeyPermission.allows``) before this
    is reached, so the method itself needs no second look here:
      1. ``read`` keys reach only GET/HEAD/OPTIONS.
      2. ``read_write`` keys add POST/PUT/PATCH.
      3. ``full_access`` keys add DELETE.

    Note the third case: an earlier version of this docstring said DELETE was
    blocked for all API keys, which stopped being true when ``full_access``
    was introduced. A ``full_access`` service-account request does reach this
    check on DELETE and is allowed through — object-level ownership is not
    consulted, because a service account is org-wide by design. That tier is
    the only thing standing between an API key and deleting any resource in
    the organization, so grant it deliberately.
    """
    return getattr(request.user, "is_service_account", False)


def has_group_access(user: Any, obj: Any) -> bool:
    """Check if a user has access to a resource via group membership.

    Reads from the polymorphic ``ResourceGroupShare`` table rather than a
    per-resource ``shared_groups`` M2M (see UN-2977). Callers can OR this
    in safely for any resource — non-shareable objects yield no rows.
    """
    # Lazy import — ``permissions`` is imported by `account_v2`/`api_v2`
    # before `tenant_account_v2` finishes loading.
    from django.contrib.contenttypes.models import ContentType
    from tenant_account_v2.models import ResourceGroupShare

    user_group_ids = user.group_memberships.values_list("group_id", flat=True)
    return ResourceGroupShare.objects.filter(
        content_type=ContentType.objects.get_for_model(type(obj)),
        object_id=str(obj.pk),
        group_id__in=user_group_ids,
    ).exists()


def _is_organization_admin(request: Request) -> bool:
    """Return True if the requesting user has the org-admin role.

    Result is cached per-request to keep cost at one membership lookup per
    incoming HTTP call regardless of how many permission classes ask.
    """
    cached = getattr(request, _REQUEST_ADMIN_CACHE_ATTR, None)
    if cached is not None:
        return cached
    is_admin = OrganizationMemberService.is_user_organization_admin(request.user)
    setattr(request, _REQUEST_ADMIN_CACHE_ATTR, is_admin)
    return is_admin


def _is_resource_owner(user: Any, obj: Any) -> bool:
    """True if ``user`` owns ``obj``.

    Resources migrated to the membership model expose ``memberships`` — owner
    means an OWNER-role row (creator + co-owners). Resources not yet migrated
    fall back to ``created_by`` (co-owners rollout, UN-2202). ``created_by`` is
    no longer consulted once a resource adopts the membership model.
    """
    memberships = getattr(obj, "memberships", None)
    if memberships is None:
        return obj.created_by == user
    from permissions.roles import ResourceRole

    return memberships.filter(user=user, role=ResourceRole.OWNER).exists()


def _is_resource_viewer(user: Any, obj: Any) -> bool:
    """True if ``user`` has direct viewer access to ``obj``.

    Symmetric to :func:`_is_resource_owner`. Resources migrated to the
    membership model expose ``memberships`` — a direct viewer is a VIEWER-role
    row (the successor to the old ``shared_users`` M2M, UN-2202 Phase 2).
    Resources not yet migrated fall back to the ``shared_users`` M2M so the
    shared permission classes keep working for both.
    """
    memberships = getattr(obj, "memberships", None)
    if memberships is None:
        return obj.shared_users.filter(pk=user.pk).exists()
    from permissions.roles import ResourceRole

    return memberships.filter(user=user, role=ResourceRole.VIEWER).exists()


class IsOwner(permissions.BasePermission):
    """Allow owners and org admins.

    Org admins can manage every resource in their organization regardless of
    ``created_by``. This matches the "admin role manages everything" model
    expected by org-to-org migration (resources land owned by a service
    account) and by typical admin UX.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        if _is_resource_owner(request.user, obj):
            return True
        if _is_organization_admin(request):
            return True
        return False


def is_workflow_mutator(request: Request, workflow: Any) -> bool:
    """Whether the request user may mutate ``workflow`` or its sub-resources.

    Admits the workflow's owner, an org admin, or a service account. Shared
    access (direct/group/org) grants read only, never mutate. Shared by the
    object-level gate (``IsParentWorkflowOwner``) and the collection-level
    ``reorder`` action, which can't use an object-permission class.
    """
    if _is_service_account(request):
        return True
    if _is_resource_owner(request.user, workflow):
        return True
    return _is_organization_admin(request)


class IsParentWorkflowOwner(permissions.BasePermission):
    """Mutation gate for nested workflow sub-resources.

    Admits only the parent workflow's owner, org admin, or service account.
    Pairs with a parent-aware queryset that admits shared-workflow rows so
    this class can return 403 -- otherwise DRF raises 404 first when the
    queryset filters the row out before object permissions run.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        return is_workflow_mutator(request, obj.workflow)


class WorkflowOwnerMutationMixin:
    """Viewset mixin gating mutation of a workflow sub-resource.

    Shared access to the parent workflow -- direct, via group, or org-wide --
    grants read only. Admits owners, co-owners, org admins and service
    accounts, via :func:`is_workflow_mutator`. Requires the resource to carry
    a ``workflow`` FK.

    ``create`` is handled separately from the rest: it is collection-level, so
    DRF never calls ``get_object()`` and ``IsParentWorkflowOwner`` cannot run.
    """

    mutation_denied_message = (
        "Only the workflow owner or an organization admin can change this."
    )

    def get_permissions(self) -> list[Any]:
        if self.action in ("update", "partial_update", "destroy"):
            return [IsParentWorkflowOwner()]
        return list(super().get_permissions())

    def perform_create(self, serializer: Any) -> None:
        # Fails closed: this mixin only guards resources that carry a parent
        # workflow, so a payload without one cannot be authorised at all.
        workflow = serializer.validated_data.get("workflow")
        if not workflow or not is_workflow_mutator(self.request, workflow):
            raise PermissionDenied(self.mutation_denied_message)
        serializer.save()


class IsParentToolOwner(permissions.BasePermission):
    """Mutation gate for Prompt Studio sub-resources owned via the parent tool.

    A ``ProfileManager`` is not a membership resource, so its access is
    inherited from the parent ``CustomTool``. Admits the tool's owner (creator +
    co-owners), org admin, or service account -- mirrors ``IsParentWorkflowOwner``
    (UN-2202). Falls back to the object's own owner when it has no parent tool
    (``prompt_studio_tool`` is nullable) to preserve legacy behaviour for
    orphan rows.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        owner_resource = obj.prompt_studio_tool or obj
        if _is_resource_owner(request.user, owner_resource):
            return True
        return _is_organization_admin(request)


class IsParentDeploymentOwner(permissions.BasePermission):
    """Mutation gate for API keys owned via the parent deployment/pipeline.

    An ``APIKey`` is not a membership resource, so its access is inherited
    from the parent ``APIDeployment`` or ``Pipeline`` (both nullable — exactly
    one is set). Admits the parent's owner (creator + co-owners), org admin,
    or service account -- mirrors ``IsParentToolOwner`` (UN-2202). Falls back
    to the key's own ``created_by`` when both parents are null.

    ``obj`` may also be the parent itself. ``create`` is a collection-level
    action, so DRF never calls ``get_object()`` for it and there is no
    ``APIKey`` yet to check — the view hands the target ``APIDeployment`` /
    ``Pipeline`` straight to ``check_object_permissions``.

    An ``APIKey`` is recognised by declaring both parent FKs; a parent by
    carrying ``memberships`` (both models use ``HasMembersMixin``). Anything
    else is **denied** rather than guessed at — an authorization gate that
    cannot identify its subject must fail closed. Note this cannot collapse to
    ``obj.api or obj.pipeline or obj``: the parents declare no ``api``
    attribute, so that raises ``AttributeError`` (500) on every ``create``.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True

        if hasattr(obj, "api") and hasattr(obj, "pipeline"):
            # An APIKey: ownership is inherited from whichever parent is set,
            # falling back to the key itself when both are null.
            owner_resource = obj.api or obj.pipeline or obj
        elif hasattr(obj, "memberships"):
            # The parent deployment/pipeline, handed over by ``create``.
            owner_resource = obj
        else:
            logger.warning(
                "IsParentDeploymentOwner received an unsupported object type "
                "%s; denying.",
                type(obj).__name__,
            )
            return False

        if _is_resource_owner(request.user, owner_resource):
            return True
        return _is_organization_admin(request)


class IsOrganizationMember(permissions.BasePermission):
    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user_organization = UserContext.get_organization()
        if user_organization is None:
            return False
        return True if obj.organization == user_organization else False


class IsOwnerOrSharedUser(permissions.BasePermission):
    """Allow owners, shared users, and org admins."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        return (
            _is_resource_owner(request.user, obj)
            or _is_resource_viewer(request.user, obj)
            or has_group_access(request.user, obj)
            or _is_organization_admin(request)
        )


class IsOwnerOrSharedUserOrSharedToOrg(permissions.BasePermission):
    """Allow owners, shared users, org-shared objects, and org admins."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if _is_service_account(request):
            return True
        return (
            _is_resource_owner(request.user, obj)
            or _is_resource_viewer(request.user, obj)
            or obj.shared_to_org
            or has_group_access(request.user, obj)
            or _is_organization_admin(request)
        )


class IsFrictionLessAdapter(permissions.BasePermission):
    """Hack for friction-less onboarding not allowing user to view or updating
    friction less adapter.

    Friction-less adapters wrap platform-owned credentials, so they remain
    blocked for everyone including org admins -- exposing them would leak
    the platform's keys.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return False
        if _is_service_account(request):
            return True
        if _is_resource_owner(request.user, obj):
            return True
        return _is_organization_admin(request)


class IsFrictionLessAdapterDelete(permissions.BasePermission):
    """Hack for friction-less onboarding Allows frticon less adapter to rmoved
    by an org member.
    """

    def has_object_permission(
        self, request: Request, view: APIView, obj: AdapterInstance
    ) -> bool:
        if obj.is_friction_less:
            return True
        if _is_resource_owner(request.user, obj):
            return True
        return _is_organization_admin(request)
