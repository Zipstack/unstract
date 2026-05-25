from typing import Any

from account_v2.custom_exceptions import DuplicateData
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpRequest
from permissions.permission import IsOwner, IsOwnerOrSharedUserOrSharedToOrg
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.prompt_profile_manager_v2.constants import (
    ProfileManagerErrors,
    ProfileManagerKeys,
)
from prompt_studio.prompt_profile_manager_v2.serializers import ProfileManagerSerializer

from .models import ProfileManager


class ProfileManagerView(viewsets.ModelViewSet):
    """Viewset to handle all Custom tool related operations."""

    versioning_class = URLPathVersioning
    serializer_class = ProfileManagerSerializer

    def get_permissions(self) -> list[Any]:
        # Mutations require ownership; reads honor sharing.
        if self.action in ("create", "destroy", "partial_update", "update"):
            return [IsOwner()]
        return [IsOwnerOrSharedUserOrSharedToOrg()]

    def get_queryset(self) -> QuerySet | None:
        queryset = ProfileManager.objects.for_user(self.request.user)
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ProfileManagerKeys.CREATED_BY,
        )
        if filter_args:
            queryset = queryset.filter(**filter_args)
        return queryset

    def create(
        self, request: HttpRequest, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        serializer: ProfileManagerSerializer = self.get_serializer(data=request.data)
        # Overriding default exception behaviour
        # TO DO : Handle model related exceptions.
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(ProfileManagerErrors.PROFILE_NAME_EXISTS)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
