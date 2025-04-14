from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.prompt_studio_index_manager_v2.constants import IndexManagerKeys
from prompt_studio.prompt_studio_index_manager_v2.serializers import (
    IndexManagerSerializer,
)

from .models import IndexManager


class IndexManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = IndexManagerSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            IndexManagerKeys.PROFILE_MANAGER,
            IndexManagerKeys.DOCUMENT_MANAGER,
        )
        queryset = None
        if filter_args:
            queryset = IndexManager.objects.filter(**filter_args)
        return queryset
