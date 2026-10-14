"""Admin-only read API for the platform audit log. See README.md for the contract."""

import csv
import io
import json

from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from drf_standardized_errors.openapi_serializers import (
    ErrorResponse403Serializer,
    ValidationErrorResponseSerializer,
)
from platform_api.permissions import IsOrganizationAdmin
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from utils.pagination import CustomPagination
from utils.user_context import UserContext

from platform_audit.actions import all_actions
from platform_audit.models import PlatformAuditEvent
from platform_audit.retention import retention_cutoff, retention_days
from platform_audit.serializers import (
    AuditActionSerializer,
    AuditActorSerializer,
    AuditEventQuerySerializer,
    ExportTooLargeResponseSerializer,
    PlatformAuditEventSerializer,
    action_label,
)

MAX_EXPORT_ROWS = 10_000
MAX_ACTORS = 1_000

# Spreadsheet apps evaluate a cell that starts with one of these as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CSV_COLUMNS = [
    "occurred_at",
    "actor_type",
    "actor_email",
    "actor_name",
    "actor_key_name",
    "action",
    "action_label",
    "target_type",
    "target_id",
    "target_name",
    "summary",
    "changes",
    "request_id",
]


class IsPlatformAuditReader(IsOrganizationAdmin):
    """Organisation admins on a session. Members, service accounts and
    platform API keys are refused.
    """

    message = "Only organization admins can read the platform audit log."


class ExportTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = (
        f"More than {MAX_EXPORT_ROWS} events match. Narrow the filter and retry."
    )
    default_code = "export_too_large"


class _AuditBaseView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsPlatformAuditReader]
    serializer_class = PlatformAuditEventSerializer
    ordering = ["-occurred_at"]
    # Newest first is the contract; ?ordering= is ignored rather than honoured.
    ordering_fields: list[str] = []

    def get_queryset(self) -> QuerySet[PlatformAuditEvent]:
        organization = UserContext.get_organization()
        if organization is None:
            raise PermissionDenied("Organization context is required.")
        return PlatformAuditEvent.objects.filter(
            organization=organization,
            occurred_at__gte=retention_cutoff(organization),
        )

    def filtered_queryset(self, request: Request) -> QuerySet[PlatformAuditEvent]:
        query = AuditEventQuerySerializer.from_query_params(request.query_params)
        query.is_valid(raise_exception=True)
        return self.filter_queryset(query.apply(self.get_queryset()))


_FILTER_PARAMETERS = [
    OpenApiParameter(
        "action",
        OpenApiTypes.STR,
        many=True,
        explode=True,
        description="Action key; repeat to match any of several. "
        "Keys come from platform/audit/actions/. An unknown key is a 400.",
    ),
    OpenApiParameter(
        "actor",
        OpenApiTypes.EMAIL,
        description="Actor e-mail, case-insensitive exact match.",
    ),
    OpenApiParameter(
        "from",
        OpenApiTypes.STR,
        description="ISO date or datetime, inclusive. Defaults to the start "
        "of the retention window.",
    ),
    OpenApiParameter(
        "to",
        OpenApiTypes.STR,
        description="ISO date or datetime, inclusive; a date covers the whole day.",
    ),
    OpenApiParameter(
        "search",
        OpenApiTypes.STR,
        description="Case-insensitive substring of the actor e-mail, actor "
        "name, key name, target name or summary.",
    ),
]

# drf-standardized-errors does not add these for query-parameter GET views.
_ERRORS = {
    400: ValidationErrorResponseSerializer,
    403: ErrorResponse403Serializer,
}
# Every view reads the default ordering filter; none takes ?ordering=.
_NO_ORDERING = OpenApiParameter("ordering", exclude=True)

_EXAMPLE_EVENT = {
    "id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90",
    "occurred_at": "2026-10-15T09:30:12.481000Z",
    "actor": {
        "id": 42,
        "email": "priya@acme.com",
        "name": "Priya Raman",
        "type": "user",
        "key_id": "",
        "key_name": "",
    },
    "action": "member.role_changed",
    "action_label": "Role changed",
    "target": {"type": "member", "id": "57", "name": "sam@acme.com"},
    "summary": "user → admin",
    "changes": {"before": {"role": "user"}, "after": {"role": "admin"}},
    "request_id": "6c1f0f2e-8d0e-4b8e-9a51-1b2f3e4d5c6a",
}


class PlatformAuditEventListView(_AuditBaseView):
    pagination_class = CustomPagination

    @extend_schema(
        operation_id="platform_audit_events_list",
        tags=["platform-audit"],
        parameters=[
            *_FILTER_PARAMETERS,
            OpenApiParameter("page", OpenApiTypes.INT, description="1-based page."),
            OpenApiParameter(
                "page_size", OpenApiTypes.INT, description="Default 50, max 1000."
            ),
            _NO_ORDERING,
        ],
        responses={
            200: inline_serializer(
                name="PlatformAuditEventPage",
                fields={
                    "count": serializers.IntegerField(),
                    "next": serializers.URLField(allow_null=True),
                    "previous": serializers.URLField(allow_null=True),
                    "retention_days": serializers.IntegerField(),
                    "results": PlatformAuditEventSerializer(many=True),
                },
            ),
            **_ERRORS,
        },
        examples=[
            OpenApiExample(
                "One page",
                response_only=True,
                value={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "retention_days": 90,
                    "results": [_EXAMPLE_EVENT],
                },
            )
        ],
        description="Events in the retention window, newest first.",
    )
    def get(self, request: Request) -> Response:
        queryset = self.filtered_queryset(request)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["retention_days"] = retention_days(UserContext.get_organization())
        return response


class PlatformAuditEventExportView(_AuditBaseView):
    @extend_schema(
        operation_id="platform_audit_events_export",
        tags=["platform-audit"],
        parameters=[*_FILTER_PARAMETERS, _NO_ORDERING],
        responses={
            (200, "text/csv"): OpenApiResponse(
                OpenApiTypes.STR,
                description="CSV attachment; columns: " + ", ".join(CSV_COLUMNS),
            ),
            **_ERRORS,
            413: OpenApiResponse(
                ExportTooLargeResponseSerializer,
                description=f"More than {MAX_EXPORT_ROWS} rows match the filter "
                "(code export_too_large).",
            ),
        },
        description="The list filter as a CSV download, newest first.",
    )
    def get(self, request: Request) -> HttpResponse:
        queryset = self.filtered_queryset(request)
        # One query with a cap+1 sentinel instead of a separate COUNT.
        rows = list(queryset[: MAX_EXPORT_ROWS + 1])
        if len(rows) > MAX_EXPORT_ROWS:
            raise ExportTooLarge()
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(_build_csv(rows), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="platform_audit_{timestamp}.csv"'
        )
        return response


class PlatformAuditActionListView(_AuditBaseView):
    pagination_class = None

    @extend_schema(
        operation_id="platform_audit_actions_list",
        tags=["platform-audit"],
        parameters=[_NO_ORDERING],
        responses={200: AuditActionSerializer(many=True), 403: _ERRORS[403]},
        description="The action vocabulary: every key an event can carry.",
    )
    def get(self, request: Request) -> Response:
        data = [
            {"key": a.key, "label": a.label, "category": a.category}
            for a in all_actions()
        ]
        return Response(AuditActionSerializer(data, many=True).data)


class PlatformAuditActorListView(_AuditBaseView):
    pagination_class = None

    @extend_schema(
        operation_id="platform_audit_actors_list",
        tags=["platform-audit"],
        parameters=[_NO_ORDERING],
        responses={200: AuditActorSerializer(many=True), 403: _ERRORS[403]},
        description="Actors with an event in the retention window, one per "
        "identity (type, e-mail, key), including removed members and deleted "
        f"keys. At most {MAX_ACTORS}, sorted by e-mail.",
    )
    def get(self, request: Request) -> Response:
        # One row per identity (type, e-mail, key), named as on its newest event,
        # so a renamed member or key appears once. Rows without an e-mail (the
        # system actor) are left out: the ``actor`` filter cannot select them.
        identity = ("actor_type", "actor_email", "actor_key_id")
        rows = (
            self.get_queryset()
            .exclude(actor_email="")
            .order_by(*identity, "-occurred_at")
            .distinct(*identity)
            .values(
                "actor_id",
                "actor_email",
                "actor_name",
                "actor_type",
                "actor_key_id",
                "actor_key_name",
            )
        )
        data = sorted(
            (
                {
                    "id": row["actor_id"],
                    "email": row["actor_email"],
                    "name": row["actor_name"],
                    "type": row["actor_type"],
                    "key_id": row["actor_key_id"],
                    "key_name": row["actor_key_name"],
                }
                for row in rows[:MAX_ACTORS]
            ),
            key=lambda actor: (actor["email"], actor["key_name"]),
        )
        return Response(AuditActorSerializer(data, many=True).data)


def _build_csv(rows: list[PlatformAuditEvent]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for event in rows:
        writer.writerow(
            [
                _cell(value)
                for value in (
                    event.occurred_at.isoformat(),
                    event.actor_type,
                    event.actor_email,
                    event.actor_name,
                    event.actor_key_name,
                    event.action,
                    action_label(event.action),
                    event.target_type,
                    event.target_id,
                    event.target_name,
                    event.summary,
                    json.dumps(event.changes, sort_keys=True) if event.changes else "",
                    event.request_id,
                )
            ]
        )
    return output.getvalue()


def _cell(value: str) -> str:
    """Neutralise a cell a spreadsheet would run as a formula (CSV injection)."""
    if value and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
