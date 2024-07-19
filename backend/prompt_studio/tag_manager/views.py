from permissions.permission import IsOwner
from prompt_studio.tag_manager.helper import TagHelper
from prompt_studio.tag_manager.models import TagManager
from prompt_studio.tag_manager.serializers import TagManagerSerializer
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from backend.pagination import DefaultPagination


class TagManagerView(viewsets.ModelViewSet):
    """Viewset to handle all Custom tool related operations."""

    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    queryset = TagManager.objects.all()
    serializer_class = TagManagerSerializer
    pagination_class = DefaultPagination

    def list(self, request, tool_id, *args, **kwargs):
        queryset = self.get_queryset().filter(tool_id=tool_id).order_by("created_at")
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_queryset, many=True)
        paginated_response = paginator.get_paginated_response(serializer.data)
        # Convert to dict to modify the response
        paginated_response_data = paginated_response.data
        # Check if queryset is not empty
        if queryset:
            tool = queryset[0].tool
            paginated_response_data["active"] = tool.tag_id
        else:
            paginated_response_data["active"] = None

        # Return the modified response
        return Response(data=paginated_response_data, status=status.HTTP_200_OK)

    def load_checked_in_tag(self, request, tool_id, tag):
        TagHelper.load_tag(
            tool_id=tool_id,
            tag=tag,
        )
        return Response(status=status.HTTP_200_OK)

    def prompt_studio_check_in(self, request, tool_id, tag):
        return TagHelper.create_tag(
            tool_id=tool_id,
            tag=tag,
        )
