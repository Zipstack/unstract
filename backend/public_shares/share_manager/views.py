import logging
from typing import Any, Optional

from django.db.models import QuerySet
from public_shares.share_manager.helpers.prompt_share_manager_helper import (
    PromptShareManagerHelper,
)
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from .models import ShareManager
from .serializers import ShareSerializer

logger = logging.getLogger(__name__)


class ShareViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = ShareManager.objects.all()
    serializer_class = ShareSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        created_by = self.request.query_params.get("created_by")
        if created_by is not None:
            queryset = ShareManager.objects.filter(created_by=created_by)
            return queryset
        elif created_by is None:
            queryset = ShareManager.objects.all()
            return queryset

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        share_instance: ShareManager = self.get_object()
        share_id = share_instance.share_id
        PromptShareManagerHelper.unlink_prompt_studio(share_id)
        return super().destroy(request, *args, **kwargs)
