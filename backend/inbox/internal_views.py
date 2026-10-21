"""Internal endpoint the daily purge task calls."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from inbox.models import InboxItem

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
PURGE_BATCH = 5000


# Each batch commits on its own, so a run cut short keeps what it deleted.
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class PurgeInboxAPIView(APIView):
    """Delete items older than the retention window, in every organization."""

    def post(self, request: Request) -> Response:
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        old = InboxItem._base_manager.filter(created_at__lt=cutoff)
        deleted = 0
        while batch := list(old.values_list("pk", flat=True)[:PURGE_BATCH]):
            deleted += InboxItem._base_manager.filter(pk__in=batch).delete()[0]
        logger.info("Inbox purge deleted %s items older than %s", deleted, cutoff)
        return Response({"deleted": deleted})
