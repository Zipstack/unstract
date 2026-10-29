from drf_spectacular.utils import extend_schema_serializer
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


# many=False: the list action is paginated, and without it the schema would wrap
# this page inside a second paginated envelope.
@extend_schema_serializer(many=False)
class InboxPageSerializer(serializers.Serializer):
    """Schema only: the list response."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = InboxItemSerializer(many=True)
    unread_count = serializers.IntegerField()

    class Meta:
        ref_name = "InboxPage"


class InboxReadSerializer(serializers.Serializer):
    created = serializers.DateTimeField(
        required=False,
        help_text=(
            "The item's `created` as the client listed it. When the item has been "
            "refreshed since, it stays unread and the response is 409."
        ),
    )


class InboxReadConflictSerializer(serializers.Serializer):
    """The item as it is now, after a refresh the client has not seen."""

    item = InboxItemSerializer()
    unread_count = serializers.IntegerField()

    class Meta:
        ref_name = "InboxReadConflict"
