import logging
from typing import Any

from account_v2.models import User
from django.shortcuts import get_object_or_404
from plugins import get_plugin
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from tenant_account_v2.sharing_helpers import serialize_owner_refs

from permissions.membership_serializers import AddOwnerSerializer, RemoveOwnerSerializer

logger = logging.getLogger(__name__)

notification_plugin = get_plugin("notification")


class OwnerManagementMixin:
    """Owner (co-owner) management actions for a resource ViewSet.

    Owners are ``OWNER`` rows in the resource's ``memberships`` through model.
    Notifications reuse the user-sharing path (``SharingNotificationService``);
    a ViewSet opts in by setting ``notification_resource_name_field`` and
    overriding ``get_notification_resource_type``.
    """

    notification_resource_name_field: str | None = None

    def get_notification_resource_type(self, resource: Any) -> str | None:  # NOSONAR
        # Overridable hook: subclasses dispatch on ``resource`` (e.g. adapter
        # type, pipeline type); the base default ignores it.
        return None

    @action(detail=True, methods=["post"], url_path="owners")
    def add_co_owner(self, request: Request, pk: str | None = None) -> Response:
        resource = self.get_object()
        serializer = AddOwnerSerializer(
            data=request.data, context={"request": request, "resource": resource}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        added_user = User.objects.get(id=serializer.validated_data["user_id"])
        self._notify_owner_added(resource, added_user, request.user)
        return Response(
            {"id": str(resource.pk), "co_owners": self._owner_refs(resource)},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path=r"owners/(?P<user_id>[^/.]+)")
    def remove_co_owner(
        self, request: Request, pk: str | None = None, user_id: str | None = None
    ) -> Response:
        resource = self.get_object()
        user_to_remove = get_object_or_404(User, id=user_id)
        serializer = RemoveOwnerSerializer(
            data={},
            context={
                "request": request,
                "resource": resource,
                "user_to_remove": user_to_remove,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.on_owner_removed(resource, user_to_remove)
        self._notify_owner_removed(resource, user_to_remove, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def on_owner_removed(self, resource: Any, user: User) -> None:  # NOSONAR
        """Hook: resource-specific cleanup after a user loses OWNER access.

        Default no-op. The ``share`` path clears dangling defaults on access
        loss; ViewSets whose resource has such state (e.g. adapters) override
        this so ``remove_co_owner`` gets the same cleanup.
        """

    @staticmethod
    def _owner_refs(resource: Any) -> list[dict[str, Any]]:
        # Same helper every resource serializer's ``co_owners`` field uses, so
        # POST owners/ and GET list_of_shared_users cannot drift apart in either
        # roster or shape.
        return serialize_owner_refs(resource)

    # --- notifications: reuse the user-sharing service, best-effort ---

    def _notification_context(self, resource: Any) -> tuple[str, str] | None:
        if not notification_plugin or not self.notification_resource_name_field:
            return None
        resource_type = self.get_notification_resource_type(resource)
        resource_name = getattr(resource, self.notification_resource_name_field, None)
        if resource_type is None or not resource_name:
            return None
        return resource_type, resource_name

    def _notify_owner_added(self, resource: Any, user: User, actor: Any) -> None:
        ctx = self._notification_context(resource)
        if ctx is None:
            return
        resource_type, resource_name = ctx
        try:
            notification_plugin["service_class"]().send_co_owner_added_notification(
                resource_type=resource_type,
                resource_name=resource_name,
                resource_id=str(resource.pk),
                shared_by=actor,
                shared_to=[user],
                resource_instance=resource,
            )
        except Exception as e:
            logger.exception("Failed to send co-owner added notification: %s", e)

    def _notify_owner_removed(self, resource: Any, user: User, actor: Any) -> None:
        ctx = self._notification_context(resource)
        if ctx is None:
            return
        resource_type, resource_name = ctx
        try:
            notification_plugin["service_class"]().send_access_removed_notification(
                resource_type=resource_type,
                resource_name=resource_name,
                removed_from=[user],
                removed_by=actor,
                resource_id=str(resource.pk),
                resource_instance=resource,
            )
        except Exception as e:
            logger.exception("Failed to send co-owner removed notification: %s", e)
