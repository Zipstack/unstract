from typing import Optional

from django.db.models import QuerySet
from prompt_studio.prompt_studio_index_manager.constants import IndexManagerKeys
from prompt_studio.prompt_studio_index_manager.serializers import IndexManagerSerializer
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import IndexManager


class IndexManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = IndexManager.objects.all()
    serializer_class = IndexManagerSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            IndexManagerKeys.PROFILE_MANAGER,
            IndexManagerKeys.DOCUMENT_MANAGER,
        )
        if filter_args:
            queryset = IndexManager.objects.filter(**filter_args)
        else:
            queryset = IndexManager.objects.all()
        return queryset
