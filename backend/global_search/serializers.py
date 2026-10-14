"""Request validation and the response envelope.

The response serializers are the contract (see README.md); they exist for
drf-spectacular and for the shape test, while the view builds plain dicts.
"""

from rest_framework import serializers

from global_search.constants import MatchTier, SearchParams


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=SearchParams.MAX_QUERY_LENGTH,
        default="",
        help_text=(
            "Case-insensitive text matched against name and description. "
            f"Shorter than {SearchParams.MIN_QUERY_LENGTH} characters after "
            "trimming returns no groups."
        ),
    )
    types = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "Comma-separated type keys to search. Empty means all. Unknown or "
            "unavailable keys are ignored."
        ),
    )
    limit = serializers.IntegerField(
        required=False,
        default=SearchParams.DEFAULT_LIMIT,
        min_value=1,
        max_value=SearchParams.MAX_LIMIT,
        help_text="Results per type.",
    )

    def validate_types(self, value: str) -> list[str]:
        return [key for key in (part.strip() for part in value.split(",")) if key]


class SearchRouteSerializer(serializers.Serializer):
    key = serializers.CharField(help_text="Route-registry name, not a URL.")
    params = serializers.DictField(child=serializers.CharField())


class SearchResultSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.CharField()
    name = serializers.CharField()
    context = serializers.CharField(
        allow_null=True, help_text="One display line: owner or parent."
    )
    match = serializers.ChoiceField(choices=[tier.label for tier in MatchTier])
    route = SearchRouteSerializer()


class SearchGroupSerializer(serializers.Serializer):
    type = serializers.CharField()
    label = serializers.CharField()
    has_more = serializers.BooleanField()
    results = SearchResultSerializer(many=True)


class SearchResponseSerializer(serializers.Serializer):
    query = serializers.CharField(allow_blank=True)
    groups = SearchGroupSerializer(many=True)
