from api_key_usage.expiry import record_expiry_change
from api_key_usage.rotation import (
    ROTATED_FIELDS,
    RotateSerializer,
    grace_summary,
    rotate_secret,
)
from api_v2.models import APIDeployment
from django.db.models import Prefetch
from platform_api.permissions import is_org_admin_session
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import (
    best_effort,
    record_key_update,
    record_platform_event,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.user_context import UserContext

from global_api_deployment_key.models import (
    GlobalApiDeploymentKey,
    deployments_keyable_by,
)
from global_api_deployment_key.permissions import CanManageApiKeys, IsOrganizationAdmin
from global_api_deployment_key.serializers import (
    ApiDeploymentMinimalSerializer,
    GlobalApiDeploymentKeyCreateSerializer,
    GlobalApiDeploymentKeyDetailSerializer,
    GlobalApiDeploymentKeyListSerializer,
    GlobalApiDeploymentKeyUpdateSerializer,
)


class GlobalApiDeploymentKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get_permissions(self):
        # Members the org lets manage keys may list, create, view and rotate,
        # and pick deployments (UN-4399); editing and deleting stay admin-only.
        if self.action in ("list", "create", "retrieve", "rotate", "deployments"):
            return [IsAuthenticated(), CanManageApiKeys()]
        return super().get_permissions()

    def _is_admin(self) -> bool:
        return is_org_admin_session(self.request, self)

    def _limit_member(self, allow_all: bool, deployment_ids) -> None:
        """A member only keys deployments they own (``deployments_keyable_by``),
        never every deployment. Viewing or rotating
        a key (both reveal the secret) is held to the same rule.
        """
        if self._is_admin():
            return
        if allow_all:
            raise PermissionDenied(
                "Only organisation admins can use keys for all deployments."
            )
        accessible = set(
            deployments_keyable_by(self.request.user).values_list("pk", flat=True)
        )
        if not set(deployment_ids) <= accessible:
            raise PermissionDenied("Members can only use keys for deployments they own.")

    def _limit_member_to_key(self, instance: GlobalApiDeploymentKey) -> None:
        # Only keys they created as a member: another user's key would hand
        # them its secret (retrieve) or break their integration (rotate), and a
        # key they created while an admin is org-level, not bound to them.
        if not self._is_admin() and (
            instance.created_by_id != self.request.user.id
            or not instance.created_by_member
        ):
            raise PermissionDenied(
                "Members can only view or rotate keys they created as a member."
            )
        self._limit_member(
            instance.allow_all_deployments,
            instance.api_deployments.values_list("pk", flat=True),
        )

    def get_queryset(self):
        # ``created_by`` is select_related because the list serializer reads
        # ``created_by.email`` per row; without it the unpaginated list costs
        # one extra query per key.
        keys = GlobalApiDeploymentKey.objects.filter(
            organization=UserContext.get_organization(),
        ).select_related("created_by")
        if self.action == "list" and not self._is_admin():
            # A member's list shows their own keys only: other keys name
            # deployments the member may not be able to see. Within those, only
            # the deployments they still own, so one they lost stops showing
            # its live name and status.
            return keys.filter(
                created_by=self.request.user, created_by_member=True
            ).prefetch_related(
                Prefetch(
                    "api_deployments",
                    queryset=deployments_keyable_by(self.request.user),
                )
            )
        return keys.prefetch_related("api_deployments")

    def get_serializer_class(self):
        # create/retrieve/partial_update/rotate are overridden and instantiate
        # their serializers directly, so only ``list``/``destroy`` (and DRF's
        # default fallback) route through here — all use the list serializer.
        return GlobalApiDeploymentKeyListSerializer

    def create(self, request, *args, **kwargs):
        serializer = GlobalApiDeploymentKeyCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        self._limit_member(
            serializer.validated_data.get("allow_all_deployments", False),
            [d.pk for d in serializer.validated_data.get("api_deployments") or []],
        )
        instance = serializer.save(created_by_member=not self._is_admin())
        _record_key_event(
            request,
            Action.KEY_CREATED,
            instance.id,
            instance.name,
            changes={"after": _key_fields(instance)},
        )
        _record_expiry_change(request, instance, before=None)
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._limit_member_to_key(instance)
        serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        before = _key_fields(instance)
        expires_before = instance.expires_at
        serializer = GlobalApiDeploymentKeyUpdateSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        if instance.created_by_member:
            _limit_to_creator(instance, serializer.validated_data)
        updated_instance = serializer.save()
        _record_key_update(request, updated_instance, before)
        _record_expiry_change(request, updated_instance, before=expires_before)
        response_serializer = GlobalApiDeploymentKeyListSerializer(updated_instance)
        return Response(response_serializer.data)

    def rotate(self, request, *args, **kwargs):
        instance = self.get_object()
        self._limit_member_to_key(instance)
        options = RotateSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        rotate_secret(instance, options.validated_data["grace"])
        instance.modified_by = request.user
        instance.save(update_fields=[*ROTATED_FIELDS, "modified_by", "modified_at"])
        _record_key_event(
            request,
            Action.KEY_ROTATED,
            instance.id,
            instance.name,
            summary=grace_summary(instance),
        )
        response_serializer = GlobalApiDeploymentKeyDetailSerializer(instance)
        return Response(response_serializer.data)

    def perform_destroy(self, instance):
        key_id, key_name, before = instance.id, instance.name, _key_fields(instance)
        instance.delete()
        _record_key_event(
            self.request, Action.KEY_REVOKED, key_id, key_name, changes={"before": before}
        )

    @action(detail=False, methods=["get"])
    def deployments(self, request):
        """API deployments the caller may assign to keys: all of the org's for
        admins, the ones they own for members.
        """
        organization = UserContext.get_organization()
        deployments = APIDeployment.objects.filter(organization=organization)
        if not self._is_admin():
            deployments = deployments_keyable_by(request.user)
        serializer = ApiDeploymentMinimalSerializer(deployments, many=True)
        return Response(serializer.data)


@best_effort
def _key_fields(key: GlobalApiDeploymentKey) -> dict:
    """The audited fields. Never the key value itself."""
    return {
        "description": key.description,
        "is_active": key.is_active,
        "allow_all_deployments": key.allow_all_deployments,
        "api_deployments": sorted(
            str(pk) for pk in key.api_deployments.all().values_list("pk", flat=True)
        ),
    }


def _limit_to_creator(key: GlobalApiDeploymentKey, validated: dict) -> None:
    """An edit may never open a member-created key to all deployments (a new
    key does that), nor add a deployment its creator may not key
    (``deployments_keyable_by``), outside which the key never works.
    """
    message = (
        "This key was created by a member and only works for deployments they "
        "own. Create a new key instead."
    )
    if validated.get("allow_all_deployments"):
        raise ValidationError({"allow_all_deployments": message})
    if "api_deployments" not in validated:
        return
    # Only additions: the edit form resends the current list, which may name
    # deployments the creator has since lost (the key just stops working there).
    added = {d.pk for d in validated["api_deployments"]} - set(
        key.api_deployments.values_list("pk", flat=True)
    )
    if not added:
        return
    accessible = set(deployments_keyable_by(key.created_by).values_list("pk", flat=True))
    if not added <= accessible:
        raise ValidationError({"api_deployments": message})


def _record_key_event(request, action: Action, key_id, key_name: str, **kwargs) -> None:
    record_platform_event(
        action=action,
        target_type=TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        target_id=key_id,
        target_name=key_name,
        request=request,
        **kwargs,
    )


@best_effort
def _record_expiry_change(request, key: GlobalApiDeploymentKey, before) -> None:
    record_expiry_change(
        request,
        target_type=TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        key=key,
        before=before,
    )


@best_effort
def _record_key_update(request, key: GlobalApiDeploymentKey, before: dict) -> None:
    record_key_update(
        target_type=TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        key=key,
        before=before,
        after=_key_fields(key),
        request=request,
    )
