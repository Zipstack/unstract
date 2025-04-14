from typing import Any

from account.custom_exceptions import DuplicateData
from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from prompt.constants import PromptErrors

from .models import Prompt
from .serializers import PromptSerializer


class PromptViewSet(viewsets.ModelViewSet):
    """Used to view and edit prompts.

    Handles GET,POST,PUT,PATCH and DELETE
    """

    versioning_class = URLPathVersioning
    queryset = Prompt.objects.all()
    serializer_class = PromptSerializer

    @action(detail=False)
    def get_all_prompt(self, request: Request) -> Response:
        # has not specific funstions. Added for testing purpose
        serializer = self.get_serializer(many=True)
        return Response(serializer.data)

    def create(self, request: Any) -> Response:
        # Overriding default exception behaviour
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{PromptErrors.PROMPT_EXISTS}, {PromptErrors.DUPLICATE_API}"
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
