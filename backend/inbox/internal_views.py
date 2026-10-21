"""Internal endpoint the daily purge task calls."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from inbox.models import InboxItem

RETENTION_DAYS = 90
PURGE_BATCH = 5000


class PurgeInboxAPIView(APIView):
    """Delete items older than the retention window, in every organization."""

    def post(self, request: Request) -> Response:
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        old = InboxItem._base_manager.filter(created_at__lt=cutoff)
        deleted = 0
        # Batches keep each transaction short; a killed run keeps what it deleted.
        while batch := list(old.values_list("pk", flat=True)[:PURGE_BATCH]):
            deleted += InboxItem._base_manager.filter(pk__in=batch).delete()[0]
        return Response({"deleted": deleted})
