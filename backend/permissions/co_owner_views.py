"""Shared mixin for co-owner management actions across resource types."""

import logging
from typing import Any

from account_v2.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from permissions.co_owner_serializers import AddCoOwnerSerializer, RemoveCoOwnerSerializer

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

    def _send_co_owner_notification(
        self, resource: Any, user: User, request: Request
    ) -> None:
        """Send an email notification to a newly added co-owner.

        Does nothing when the notification plugin is not installed (OSS)
        or when the ViewSet has not opted in.
        """
        from plugins import get_plugin

        plugin = get_plugin("notification")
        if not plugin:
            return

        resource_type = self.get_notification_resource_type(resource)
        if not resource_type:
            return

        name_field = self.notification_resource_name_field
        if not name_field:
            return

        resource_name = getattr(resource, name_field, None) or ""

        try:
            service = plugin["service_class"]()
            service.send_sharing_notification(
                resource_type=resource_type,
                resource_name=resource_name,
                resource_id=str(resource.pk),
                shared_by=request.user,
                shared_to=[user],
                resource_instance=resource,
            )
        except Exception:
            logger.exception(
                "Failed to send co-owner notification for %s %s",
                resource.__class__.__name__,
                resource.pk,
            )

    @action(detail=True, methods=["post"], url_path="owners")
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
            "Co-owner %s added to %s %s by %s",
            user.email,
            resource.__class__.__name__,
            resource.pk,
            request.user.email,
        )

        self._send_co_owner_notification(resource, user, request)

        co_owners = [{"id": u.id, "email": u.email} for u in resource.co_owners.all()]
        return Response(
            {"id": str(resource.pk), "co_owners": co_owners},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path="owners/(?P<user_id>[^/.]+)",
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
            "Owner %s removed from %s %s by %s",
            user_to_remove.email,
            resource.__class__.__name__,
            resource.pk,
            request.user.email,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
