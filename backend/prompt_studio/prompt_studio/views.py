import logging
from typing import Any, Optional

from account.custom_exceptions import DuplicateData
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpRequest
from prompt_studio.prompt_studio.constants import (
    ToolStudioPromptErrors,
    ToolStudioPromptKeys,
)
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import ToolStudioPrompt
from .serializers import ToolStudioPromptSerializer

logger = logging.getLogger(__name__)


class ToolStudioPromptView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics.

    Args:
        viewsets (_type_)

    Raises:
        DuplicateData
        FilenameMissingError
        IndexingError
        ValidationError
    """

    versioning_class = URLPathVersioning
    serializer_class = ToolStudioPromptSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        if filter_args:
            queryset = ToolStudioPrompt.objects.filter(
                created_by=self.request.user, **filter_args
            )
        else:
            queryset = ToolStudioPrompt.objects.filter(
                created_by=self.request.user,
            )
        return queryset

    def create(
        self, request: HttpRequest, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        serializer = self.get_serializer(data=request.data)
        # TODO : Handle model related exceptions.
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolStudioPromptErrors.PROMPT_NAME_EXISTS}, \
                    {ToolStudioPromptErrors.DUPLICATE_API}"
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
