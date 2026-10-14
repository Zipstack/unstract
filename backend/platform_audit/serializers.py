from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from platform_audit.actions import get_action
from platform_audit.models import ActorType, PlatformAuditEvent

SEARCH_MAX_LENGTH = 200


class _DateOrDateTimeField(serializers.Field):
    """An ISO date (``2026-10-15``) or datetime (``2026-10-15T09:30:00Z``).

    A date is returned as a ``date`` so the caller can decide which end of the
    day it means; a naive datetime is read in the server's time zone.
    """

    default_error_messages = {
        "invalid": "Use an ISO 8601 date (YYYY-MM-DD) or datetime.",
    }

    def to_internal_value(self, data: Any) -> date | datetime:
        value = str(data).strip()
        try:
            # Date first: parse_datetime also accepts a bare date (as midnight),
            # which would lose "a date ``to`` covers the whole day".
            parsed_date = parse_date(value)
            if parsed_date is not None:
                return parsed_date
            parsed_datetime = parse_datetime(value)
        except ValueError:
            parsed_datetime = None
        if parsed_datetime is None:
            self.fail("invalid")
        if timezone.is_naive(parsed_datetime):
            parsed_datetime = timezone.make_aware(parsed_datetime)
        return parsed_datetime

    def to_representation(self, value: Any) -> str:
        return value.isoformat()


def _start_of(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


class AuditEventQuerySerializer(serializers.Serializer):
    """Validates the filters shared by the list and export endpoints.

    Build it with :meth:`from_query_params`, which reads the repeatable
    ``action`` parameter. ``from`` is a Python keyword, so the field is
    declared as ``from_`` and renamed in :meth:`get_fields`; errors then
    report ``attr: "from"``, the parameter's real name.
    """

    action = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False
    )
    actor = serializers.CharField(max_length=254, required=False, allow_blank=True)
    from_ = _DateOrDateTimeField(required=False)
    to = _DateOrDateTimeField(required=False)
    search = serializers.CharField(
        max_length=SEARCH_MAX_LENGTH, required=False, allow_blank=True
    )

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["from"] = fields.pop("from_")
        return fields

    @classmethod
    def from_query_params(cls, query_params: Any) -> "AuditEventQuerySerializer":
        # A blank value (a cleared date picker, ``?action=``) means "no filter".
        data: dict[str, Any] = {
            "action": [a for a in query_params.getlist("action") if a.strip()]
        }
        for param in ("actor", "from", "to", "search"):
            # The last non-blank value: ``?from=X&from=`` keeps X rather than
            # silently dropping the bound.
            values = [v for v in query_params.getlist(param) if v.strip()]
            if values:
                data[param] = values[-1]
        return cls(data=data)

    def validate_action(self, value: list[str]) -> list[str]:
        unknown = sorted({key for key in value if get_action(key) is None})
        if unknown:
            raise serializers.ValidationError(
                f"Unknown action: {', '.join(unknown)}. See platform/audit/actions/."
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = self._window(attrs)
        if start is not None and end is not None and start >= end:
            raise serializers.ValidationError({"from": "Must not be after 'to'."})
        attrs["start"], attrs["end"] = start, end
        return attrs

    @staticmethod
    def _window(
        attrs: dict[str, Any],
    ) -> tuple[datetime | None, datetime | None]:
        """Turn ``from``/``to`` into a half-open ``[start, end)`` interval.

        A date ``to`` covers that whole day; a datetime ``to`` is inclusive.
        """
        start = attrs.get("from")
        if isinstance(start, date) and not isinstance(start, datetime):
            start = _start_of(start)
        end = attrs.get("to")
        try:
            if isinstance(end, datetime):
                end = end + timedelta(microseconds=1)
            elif isinstance(end, date):
                end = _start_of(end + timedelta(days=1))
        except OverflowError:
            end = None  # the end of the calendar: no upper bound
        return start, end

    def apply(self, queryset: QuerySet[PlatformAuditEvent]) -> QuerySet:
        data = self.validated_data
        if data.get("action"):
            queryset = queryset.filter(action__in=data["action"])
        actor = (data.get("actor") or "").strip().lower()
        if actor:
            queryset = queryset.filter(actor_email=actor)
        if data["start"] is not None:
            queryset = queryset.filter(occurred_at__gte=data["start"])
        if data["end"] is not None:
            queryset = queryset.filter(occurred_at__lt=data["end"])
        search = (data.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(actor_email__icontains=search)
                | Q(actor_name__icontains=search)
                | Q(actor_key_name__icontains=search)
                | Q(target_name__icontains=search)
                | Q(summary__icontains=search)
            )
        return queryset


class AuditActorSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True, help_text="Null once deleted.")
    email = serializers.CharField(allow_blank=True)
    name = serializers.CharField(allow_blank=True)
    type = serializers.ChoiceField(choices=ActorType.choices)
    key_id = serializers.CharField(allow_blank=True)
    key_name = serializers.CharField(allow_blank=True)


class AuditTargetSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.CharField(allow_blank=True)
    name = serializers.CharField(allow_blank=True)


class AuditChangesSerializer(serializers.Serializer):
    before = serializers.DictField(required=False)
    after = serializers.DictField(required=False)


class PlatformAuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    action_label = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    changes = AuditChangesSerializer()

    class Meta:
        model = PlatformAuditEvent
        fields = [
            "id",
            "occurred_at",
            "actor",
            "action",
            "action_label",
            "target",
            "summary",
            "changes",
            "request_id",
        ]
        read_only_fields = fields

    @extend_schema_field(AuditActorSerializer)
    def get_actor(self, obj: PlatformAuditEvent) -> dict[str, Any]:
        return actor_payload(obj)

    def get_action_label(self, obj: PlatformAuditEvent) -> str:
        return action_label(obj.action)

    @extend_schema_field(AuditTargetSerializer)
    def get_target(self, obj: PlatformAuditEvent) -> dict[str, Any]:
        return {"type": obj.target_type, "id": obj.target_id, "name": obj.target_name}


def actor_payload(obj: PlatformAuditEvent) -> dict[str, Any]:
    return {
        "id": obj.actor_id,
        "email": obj.actor_email,
        "name": obj.actor_name,
        "type": obj.actor_type,
        "key_id": obj.actor_key_id,
        "key_name": obj.actor_key_name,
    }


def action_label(key: str) -> str:
    """The registered label, or the raw key for an action no longer registered."""
    action = get_action(key)
    return action.label if action else key


class AuditActionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    category = serializers.CharField()


class ClientErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    attr = serializers.CharField(allow_null=True)


class ExportTooLargeResponseSerializer(serializers.Serializer):
    """Schema only: the 413 body, in the project's standard error envelope."""

    type = serializers.ChoiceField(choices=["client_error"])
    errors = ClientErrorSerializer(many=True)
