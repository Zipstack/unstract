from backend.serializers import AuditSerializer

from .models import IndexManager


class IndexManagerSerializer(AuditSerializer):
    class Meta:
        model = IndexManager
        # index_error is provider text; the document list shows it to the
        # tool's users. This view is scoped to the org only.
        exclude = ["index_error"]
