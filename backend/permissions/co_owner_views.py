"""Shared mixin for co-owner management actions across resource types."""

import logging
from typing import Any

from account_v2.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from permissions.co_owner_serializers import (
    AddCoOwnerSerializer,
    RemoveCoOwnerSerializer,
)

logger = logging.getLogger(__name__)


class CoOwnerManagementMixin:
    """Mixin that adds co-owner management endpoints to a ViewSet.

    Adds:
        - POST <pk>/owners/     -> add_co_owner
        - DELETE <pk>/owners/<user_id>/ -> remove_co_owner

    Subclasses can opt in to co-owner email notifications by setting:
        notification_resource_name_field = "<model_field>"
    and overriding:
        get_notification_resource_type(resource) -> str | None
    """

    notification_resource_name_field: str | None = None

    def get_notification_resource_type(self, resource: Any) -> str | None:
        """Return the ResourceType value for notifications, or None to skip."""
        return None

    def _get_notification_context(self, resource: Any) -> tuple[str, str] | None:
        """Return (resource_type, resource_name) or None if not opted in."""
        resource_type = self.get_notification_resource_type(resource)
        if not resource_type:
            return None

        name_field = self.notification_resource_name_field
        if not name_field:
            return None

        resource_name: str = getattr(resource, name_field, None) or ""
        return resource_type, resource_name

    def _send_co_owner_added_notification(
        self, resource: Any, user: User, request: Request
    ) -> None:
        """Send an email notification to a newly added co-owner.

        Does nothing when the notification plugin is not installed (OSS)
        or when the ViewSet has not opted in.
        """
        ctx = self._get_notification_context(resource)
        if not ctx:
            return

        resource_type, resource_name = ctx

        try:
            from plugins.notification.co_owner_notification import (
                CoOwnerNotificationService,
            )

            service = CoOwnerNotificationService()
            service.send_co_owner_added_notification(
                resource_type=resource_type,
                resource_name=resource_name,
                resource_id=str(resource.pk),
                added_by=request.user,
                added_users=[user],
                resource_instance=resource,
            )
        except Exception:
            logger.exception(
                "Failed to send co-owner added notification for %s %s",
                resource.__class__.__name__,
                resource.pk,
            )

    def _send_co_owner_revoked_notification(
        self, resource: Any, user: User, request: Request
    ) -> None:
        """Send an email notification to a removed co-owner.

        Does nothing when the notification plugin is not installed (OSS)
        or when the ViewSet has not opted in.
        """
        ctx = self._get_notification_context(resource)
        if not ctx:
            return

        resource_type, resource_name = ctx

        try:
            from plugins.notification.co_owner_notification import (
                CoOwnerNotificationService,
            )

            service = CoOwnerNotificationService()
            service.send_co_owner_revoked_notification(
                resource_type=resource_type,
                resource_name=resource_name,
                resource_id=str(resource.pk),
                removed_by=request.user,
                removed_users=[user],
                resource_instance=resource,
            )
        except Exception:
            logger.exception(
                "Failed to send co-owner revoked notification for %s %s",
                resource.__class__.__name__,
                resource.pk,
            )

    def add_co_owner(self, request: Request, pk: Any = None) -> Response:
        """Add a co-owner to the resource."""
        resource = self.get_object()  # type: ignore[attr-defined]

        serializer = AddCoOwnerSerializer(
            data=request.data,
            context={"request": request, "resource": resource},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        user = User.objects.get(id=serializer.validated_data["user_id"])
        logger.info(
            "Co-owner user_id=%s added to %s %s by user_id=%s",
            user.id,
            resource.__class__.__name__,
            resource.pk,
            request.user.id,
        )

        self._send_co_owner_added_notification(resource, user, request)

        co_owners = [{"id": u.id, "email": u.email} for u in resource.co_owners.all()]
        return Response(
            {"id": str(resource.pk), "co_owners": co_owners},
            status=status.HTTP_200_OK,
        )

    def remove_co_owner(
        self, request: Request, pk: Any = None, user_id: Any = None
    ) -> Response:
        """Remove a co-owner from the resource."""
        resource = self.get_object()  # type: ignore[attr-defined]
        user_to_remove = get_object_or_404(User, id=user_id)

        serializer = RemoveCoOwnerSerializer(
            data={},
            context={
                "request": request,
                "resource": resource,
                "user_to_remove": user_to_remove,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            "Owner user_id=%s removed from %s %s by user_id=%s",
            user_to_remove.id,
            resource.__class__.__name__,
            resource.pk,
            request.user.id,
        )

        self._send_co_owner_revoked_notification(resource, user_to_remove, request)

        return Response(status=status.HTTP_204_NO_CONTENT)
