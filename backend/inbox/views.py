from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from utils.pagination import CustomPagination
from utils.user_context import UserContext

from inbox.models import InboxItem
from inbox.serializers import (
    InboxItemSerializer,
    InboxPageSerializer,
    InboxReadConflictSerializer,
    InboxReadSerializer,
)
from inbox.service import push_unread, unread_count


class InboxViewSet(viewsets.GenericViewSet):
    """The caller's own inbox in the current organization."""

    serializer_class = InboxItemSerializer
    pagination_class = CustomPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InboxItem.objects.filter(user=self.request.user).order_by("-created_at")

    @extend_schema(
        operation_id="inbox_list",
        tags=["inbox"],
        responses={
            200: InboxPageSerializer,
            404: OpenApiResponse(description="Page past the end; go back to page 1"),
        },
        description="Newest first. See inbox/ReadMe.md.",
    )
    def list(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        data = self.get_paginated_response(self.get_serializer(page, many=True).data).data
        data["unread_count"] = unread_count(request.user)
        return Response(data)

    @extend_schema(
        operation_id="inbox_read",
        tags=["inbox"],
        request=InboxReadSerializer,
        responses={
            204: OpenApiResponse(description="Read, or already read"),
            404: OpenApiResponse(
                description="Not the caller's item, or since withdrawn or purged"
            ),
            409: OpenApiResponse(
                InboxReadConflictSerializer,
                description=(
                    "Refreshed by a later failure since the client listed it; "
                    "left unread"
                ),
            ),
        },
    )
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        params = InboxReadSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        item = get_object_or_404(self.get_queryset(), pk=pk)
        # Only the version the client saw is marked: a failure refresh brings
        # content the user has not seen, so it stays unread.
        seen = params.validated_data.get("created", item.created_at)
        marked = InboxItem.objects.filter(
            pk=item.pk, user=request.user, read_at__isnull=True, created_at=seen
        ).update(read_at=timezone.now())
        if marked:
            push_unread(UserContext.get_organization(), [request.user.pk])
            return Response(status=status.HTTP_204_NO_CONTENT)
        current = get_object_or_404(self.get_queryset(), pk=pk)
        if current.read_at is not None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {
                "item": self.get_serializer(current).data,
                "unread_count": unread_count(request.user),
            },
            status=status.HTTP_409_CONFLICT,
        )

    @extend_schema(
        operation_id="inbox_read_all", tags=["inbox"], request=None, responses={204: None}
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        marked = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(read_at=timezone.now())
        )
        if marked:
            push_unread(UserContext.get_organization(), [request.user.pk])
        return Response(status=status.HTTP_204_NO_CONTENT)
