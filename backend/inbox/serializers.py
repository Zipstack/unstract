from rest_framework import serializers

from inbox.models import InboxItem


class InboxItemSerializer(serializers.ModelSerializer):
    created = serializers.DateTimeField(source="created_at")
    read = serializers.SerializerMethodField()
    route = serializers.JSONField(
        allow_null=True,
        help_text="{key, params} as in global search; null when there is nothing to open",
    )

    class Meta:
        model = InboxItem
        fields = ("id", "kind", "title", "body", "route", "created", "read")

    def get_read(self, item: InboxItem) -> bool:
        return item.read_at is not None
