from backend.serializers import AuditSerializer

from .models import IndexManager
from .constants import PSDMKeys

class IndexManagerSerializer(AuditSerializer):
    class Meta:
        model = IndexManager
        fields = "__all__"