"""Internal endpoint the daily purge task calls."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from inbox.models import InboxItem

RETENTION_DAYS = 90


class PurgeInboxAPIView(APIView):
    """Delete items older than the retention window, in every organization."""

    def post(self, request: Request) -> Response:
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        deleted, _ = InboxItem._base_manager.filter(created_at__lt=cutoff).delete()
        return Response({"deleted": deleted})
