from rest_framework import serializers

from inbox.models import InboxItem


class InboxRouteSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Route name; inbox/ReadMe.md lists them")
    params = serializers.DictField(child=serializers.CharField())

    class Meta:
        ref_name = "InboxRoute"


class InboxItemSerializer(serializers.ModelSerializer):
    # A plain string: new kinds are added without a client release.
    kind = serializers.CharField()
    created = serializers.DateTimeField(source="created_at")
    read = serializers.SerializerMethodField()
    route = InboxRouteSerializer(
        allow_null=True, help_text="Null when there is nothing to open"
    )

    class Meta:
        model = InboxItem
        fields = ("id", "kind", "title", "body", "route", "created", "read")

    def get_read(self, item: InboxItem) -> bool:
        return item.read_at is not None
