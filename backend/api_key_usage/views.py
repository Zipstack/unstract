from platform_api.permissions import IsOrganizationAdmin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.user_context import UserContext

from api_key_usage import reads
from api_key_usage.serializers import KeyUsageSummarySerializer


class KeyUsageSummaryView(APIView):
    """Counts of the organisation's active keys that need attention, all types."""

    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    def get(self, request):
        reads.refresh()
        counts = reads.summary(UserContext.get_organization())
        return Response(KeyUsageSummarySerializer(counts).data)
