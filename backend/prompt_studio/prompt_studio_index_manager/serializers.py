from backend.serializers import AuditSerializer

from .models import IndexManager


class IndexManagerSerializer(AuditSerializer):
    class Meta:
        model = IndexManager
        fields = "__all__"
