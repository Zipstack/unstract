"""ViewSet + permissions for org-scoped group sharing (UN-2977 / mfbt UNS-612)."""

import logging
from typing import Any

from account_v2.models import Organization
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from utils.user_context import UserContext

from tenant_account_v2.group_serializers import (
    GroupMemberAddSerializer,
    GroupMemberSerializer,
    OrganizationGroupReadSerializer,
    OrganizationGroupWriteSerializer,
    list_groups_with_member_counts,
)
from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
)

logger = logging.getLogger(__name__)


def _current_organization() -> Organization:
    organization = UserContext.get_organization()
    if organization is None:
        raise PermissionDenied("Organization context is required.")
    return organization


def _is_org_admin(request: Request) -> bool:
    """Resolve admin role for the current request user.

    Returns False on any lookup failure rather than raising — callers gate
    individual writes; viewing is allowed for all org members.
    """
    from tenant_account_v2.sharing_helpers import is_org_admin

    return is_org_admin(request.user)


def _is_admin_or_service_account(request: Request) -> bool:
    """Write gate for group management.

    Service accounts bypass authorization — they already bypass other access
    controls (see ShareAuthorizationService) and platform-key automation needs
    to manage groups and memberships.
    """
    if getattr(request.user, "is_service_account", False):
        return True
    return _is_org_admin(request)


class IsOrgAdminForWrite(BasePermission):
    """Read for any authenticated org member; write for org admins only.

    Service accounts (platform-key auth) are also allowed to write.
    """

    message = "Only organization admins can manage groups."

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return _is_admin_or_service_account(request)


class OrganizationGroupViewSet(viewsets.ModelViewSet):
    """CRUD + member management for org-scoped sharing groups."""

    permission_classes = [IsAuthenticated, IsOrgAdminForWrite]
    lookup_field = "pk"

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action in ("list", "retrieve", "members"):
            return OrganizationGroupReadSerializer
        return OrganizationGroupWriteSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["organization"] = _current_organization()
        return ctx

    def get_queryset(self) -> QuerySet[OrganizationGroup]:
        organization = _current_organization()
        return list_groups_with_member_counts(organization=organization)

    # --- list / retrieve / create / destroy ----------------------------------

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        organization = _current_organization()
        member_filter = request.query_params.get("member")
        is_admin = _is_admin_or_service_account(request)

        if member_filter == "me":
            qs = list_groups_with_member_counts(
                organization=organization, user=request.user
            )
        elif member_filter and member_filter != "me":
            if not is_admin:
                raise PermissionDenied(
                    "Only admins can query other users' group memberships."
                )
            try:
                member_id = int(member_filter)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"member": "Must be a numeric user ID."}) from exc
            qs = list_groups_with_member_counts(organization=organization).filter(
                memberships__user_id=member_id
            )
        else:
            qs = self.get_queryset()

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer: BaseSerializer) -> None:
        organization = _current_organization()
        serializer.save(
            organization=organization,
            created_by=self.request.user,
        )

    # --- members -------------------------------------------------------------

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request: Request, pk: str | None = None) -> Response:
        group = self._get_group_or_404(pk)
        if request.method == "GET":
            qs = group.memberships.select_related("user").order_by("created_at")
            data = GroupMemberSerializer(qs, many=True).data
            return Response(data)

        # POST → bulk add
        if not _is_admin_or_service_account(request):
            raise PermissionDenied(IsOrgAdminForWrite.message)
        serializer = GroupMemberAddSerializer(data=request.data, context={"group": group})
        serializer.is_valid(raise_exception=True)
        user_ids_to_add: list[int] = serializer.validated_data["user_ids_to_add"]
        GroupMembership.objects.bulk_create(
            [GroupMembership(group=group, user_id=uid) for uid in user_ids_to_add],
            ignore_conflicts=True,
        )
        return Response(
            {"added_user_ids": user_ids_to_add},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"members/(?P<user_id>[^/.]+)",
    )
    def remove_member(
        self, request: Request, pk: str | None = None, user_id: str | None = None
    ) -> Response:
        if not _is_admin_or_service_account(request):
            raise PermissionDenied(IsOrgAdminForWrite.message)
        try:
            user_id_int = int(user_id)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValidationError({"user_id": "Must be a numeric user ID."}) from exc
        group = self._get_group_or_404(pk)
        deleted, _ = group.memberships.filter(user_id=user_id_int).delete()
        if not deleted:
            raise NotFound("User is not a member of this group.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- resources shared with this group ------------------------------------

    @action(detail=True, methods=["get"], url_path="resources")
    def resources(self, request: Request, pk: str | None = None) -> Response:
        # Admin-only: this is the delete blast-radius view. Leaving it open to
        # any org member would leak names/UUIDs of resources shared with groups
        # they are not in (org admin has no implicit resource access).
        if not _is_admin_or_service_account(request):
            raise PermissionDenied(IsOrgAdminForWrite.message)
        group = self._get_group_or_404(pk)
        payload = _collect_resources_shared_with_group(group)
        return Response(payload)

    # --- helpers -------------------------------------------------------------

    def _get_group_or_404(self, pk: str | None) -> OrganizationGroup:
        organization = _current_organization()
        obj: OrganizationGroup = get_object_or_404(
            OrganizationGroup, pk=pk, organization=organization
        )
        return obj


def _collect_resources_shared_with_group(
    group: OrganizationGroup,
) -> list[dict[str, Any]]:
    """Aggregate the resources currently shared with ``group`` across types.

    Resolves each shareable model from ``SHAREABLE_RESOURCES`` via
    ``apps.get_model`` (cloud-only models absent in OSS skip cleanly), so this
    view and the cleanup signals share one source of truth and cannot drift.
    """
    from django.apps import apps

    from tenant_account_v2.shareable_resources import SHAREABLE_RESOURCES
    from tenant_account_v2.sharing_helpers import list_resources_shared_with_group

    results: list[dict[str, Any]] = []
    for resource in SHAREABLE_RESOURCES:
        try:
            model = apps.get_model(resource.app_label, resource.model_name)
        except LookupError:
            continue  # cloud-only app not installed in this deployment
        qs = list_resources_shared_with_group(group, model).values_list(
            resource.id_field, resource.name_field
        )
        for resource_id, name in qs:
            results.append(
                {
                    "resource_type": resource.kind,
                    "resource_id": str(resource_id),
                    "name": name,
                }
            )
    return results
