"""Usage fields for the key serializers, and the read endpoints' shapes."""

from typing import Any

from rest_framework import serializers

from api_key_usage.reads import USAGE_STATUSES, KeyUsage, daily_history, usage_by_key

USAGE_FIELDS = ["last_used_at", "usage_status", "calls_30d"]


class KeyUsageFieldsMixin(serializers.Serializer):
    """Adds ``USAGE_FIELDS``; list them in the serializer's ``Meta.fields``.

    A list passes every key's usage in ``context["usage"]`` (from
    ``usage_by_key``) so it costs two queries in all. Without it, each key
    looks up its own.
    """

    usage_key_type: str

    last_used_at = serializers.SerializerMethodField()
    usage_status = serializers.SerializerMethodField()
    calls_30d = serializers.SerializerMethodField()

    def _usage(self, obj: Any) -> KeyUsage:
        usage = self.context.get("usage")
        if usage is None or obj.id not in usage:
            usage = usage_by_key(self.usage_key_type, [obj])
            self.context.setdefault("usage", {}).update(usage)
        return usage[obj.id]

    def get_last_used_at(self, obj: Any) -> str | None:
        last = self._usage(obj).last_used_at
        return serializers.DateTimeField().to_representation(last) if last else None

    def get_usage_status(self, obj: Any) -> str:
        return self._usage(obj).usage_status

    def get_calls_30d(self, obj: Any) -> int:
        return self._usage(obj).calls_30d


class DailyCallsSerializer(serializers.Serializer):
    day = serializers.DateField()
    calls = serializers.IntegerField()


class KeyHistorySerializer(serializers.Serializer):
    key_id = serializers.UUIDField()
    days = DailyCallsSerializer(many=True)
    total_calls = serializers.IntegerField()
    last_used_at = serializers.DateTimeField(allow_null=True)
    usage_status = serializers.ChoiceField(choices=USAGE_STATUSES)


class KeyCallerSerializer(serializers.Serializer):
    api_deployment_id = serializers.UUIDField()
    display_name = serializers.CharField(allow_null=True)
    api_name = serializers.CharField(allow_null=True)
    calls = serializers.IntegerField()
    last_call_at = serializers.DateTimeField()


class KeyUsageCountsSerializer(serializers.Serializer):
    never_used = serializers.IntegerField()
    expiring_7d = serializers.IntegerField()
    idle_90d = serializers.IntegerField()


class KeyUsageSummarySerializer(KeyUsageCountsSerializer):
    by_type = serializers.DictField(child=KeyUsageCountsSerializer())


def history_response(key_type: str, key: Any) -> dict[str, Any]:
    """The history endpoint's body for ``key``: the window plus its usage."""
    days = daily_history(key_type, key.id)
    usage = usage_by_key(key_type, [key])[key.id]
    return KeyHistorySerializer(
        {
            "key_id": key.id,
            "days": days,
            "total_calls": sum(day["calls"] for day in days),
            "last_used_at": usage.last_used_at,
            "usage_status": usage.usage_status,
        }
    ).data
