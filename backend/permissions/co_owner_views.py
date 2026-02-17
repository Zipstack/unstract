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
    """

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
            resource.id,
            request.user.email,
        )

        co_owners = [{"id": u.id, "email": u.email} for u in resource.co_owners.all()]
        return Response(
            {"id": str(resource.id), "co_owners": co_owners},
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
            resource.id,
            request.user.email,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
