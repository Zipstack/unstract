from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from utils.pagination import CustomPagination

from inbox.models import InboxItem
from inbox.serializers import InboxItemSerializer
from inbox.service import unread_count


class InboxViewSet(viewsets.GenericViewSet):
    """The caller's own inbox in the current organization."""

    serializer_class = InboxItemSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        return InboxItem.objects.filter(user=self.request.user).order_by("-created_at")

    @extend_schema(
        operation_id="inbox_list",
        tags=["inbox"],
        responses={
            200: inline_serializer(
                "InboxPage",
                {
                    "count": serializers.IntegerField(),
                    "next": serializers.URLField(allow_null=True),
                    "previous": serializers.URLField(allow_null=True),
                    "results": InboxItemSerializer(many=True),
                    "unread_count": serializers.IntegerField(),
                },
            )
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
        request=None,
        responses={204: None, 404: OpenApiResponse(description="Not the caller's item")},
    )
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        item = get_object_or_404(self.get_queryset(), pk=pk)
        if item.read_at is None:
            item.read_at = timezone.now()
            item.save(update_fields=["read_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="inbox_read_all", tags=["inbox"], request=None, responses={204: None}
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)
