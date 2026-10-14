import csv
import io
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.utils import timezone

from platform_audit.models import PlatformAuditEvent
from platform_audit.tests.base import AuditTestBase, make_user
from platform_audit.serializers import AuditEventQuerySerializer
from platform_audit.views import (
    CSV_COLUMNS,
    PlatformAuditActionListView,
    PlatformAuditActorListView,
    PlatformAuditEventExportView,
    PlatformAuditEventListView,
)

LIST = PlatformAuditEventListView.as_view()
EXPORT = PlatformAuditEventExportView.as_view()
ACTIONS = PlatformAuditActionListView.as_view()
ACTORS = PlatformAuditActorListView.as_view()


class AuditReadApiTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.now = timezone.now()
        self.role = self._event(
            "member.role_changed",
            days_ago=1,
            target_name="sam@example.com",
            summary="user → admin",
        )
        self.rotate = self._event(
            "key.rotated", days_ago=2, target_name="ci-key", actor_email="bot@example.com"
        )
        self.group = self._event("group.created", days_ago=10, target_name="Finance")
        self.expired = self._event("group.deleted", days_ago=91, target_name="Old")
        self.foreign = self._event(
            "group.created", days_ago=1, organization=self.other_org, target_name="Theirs"
        )

    def _event(self, action: str, days_ago: float, **kwargs) -> PlatformAuditEvent:
        fields = {
            "organization": self.org,
            "occurred_at": self.now - timedelta(days=days_ago),
            "actor": self.admin,
            "actor_type": "user",
            "actor_email": "admin@example.com",
            "actor_name": "Ada Min",
            "action": action,
            "target_type": "x",
            "target_id": "1",
            **kwargs,
        }
        return PlatformAuditEvent.objects.create(**fields)

    def _get(self, view, params=None, user=None, **kwargs):
        response = self.call(view, "get", user=user, data=params or {}, **kwargs)
        return response

    def _ids(self, response) -> list[str]:
        return [row["id"] for row in response.data["results"]]

    # --- list ------------------------------------------------------------------

    def test_lists_this_org_inside_retention_newest_first(self) -> None:
        response = self._get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._ids(response),
            [str(self.role.id), str(self.rotate.id), str(self.group.id)],
        )
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["retention_days"], 90)

    def test_row_shape(self) -> None:
        row = self._get(LIST, {"action": "member.role_changed"}).data["results"][0]
        self.assertEqual(
            set(row),
            {
                "id",
                "occurred_at",
                "actor",
                "action",
                "action_label",
                "target",
                "summary",
                "changes",
                "request_id",
            },
        )
        self.assertEqual(
            row["actor"],
            {
                "id": self.admin.id,
                "email": "admin@example.com",
                "name": "Ada Min",
                "type": "user",
                "key_id": "",
                "key_name": "",
            },
        )
        self.assertEqual(row["action_label"], "Role changed")
        self.assertEqual(
            row["target"], {"type": "x", "id": "1", "name": "sam@example.com"}
        )

    def test_filters_combine(self) -> None:
        params = {
            "action": ["member.role_changed", "key.rotated"],
            "from": (self.now - timedelta(days=3)).date().isoformat(),
            "to": self.now.date().isoformat(),
        }
        self.assertEqual(
            self._ids(self._get(LIST, params)),
            [str(self.role.id), str(self.rotate.id)],
        )
        params["actor"] = "BOT@example.com"
        self.assertEqual(self._ids(self._get(LIST, params)), [str(self.rotate.id)])

    def test_search_matches_target_and_summary(self) -> None:
        self.assertEqual(
            self._ids(self._get(LIST, {"search": "FINANCE"})), [str(self.group.id)]
        )
        self.assertEqual(
            self._ids(self._get(LIST, {"search": "→ admin"})), [str(self.role.id)]
        )

    def test_date_to_covers_the_whole_day_and_datetime_to_is_inclusive(self) -> None:
        day = self.rotate.occurred_at.date()
        ids = self._ids(self._get(LIST, {"from": day.isoformat(), "to": day.isoformat()}))
        self.assertEqual(ids, [str(self.rotate.id)])
        exact = self.rotate.occurred_at.isoformat()
        self.assertEqual(
            self._ids(self._get(LIST, {"from": exact, "to": exact})),
            [str(self.rotate.id)],
        )

    def test_pagination(self) -> None:
        response = self._get(LIST, {"page_size": 2})
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["count"], 3)
        self.assertIsNotNone(response.data["next"])
        page2 = self._get(LIST, {"page_size": 2, "page": 2})
        self.assertEqual(self._ids(page2), [str(self.group.id)])

    def test_invalid_filters_are_400(self) -> None:
        for params in (
            {"action": "nope.unknown"},
            {"from": "yesterday"},
            {"from": "2026-10-10", "to": "2026-10-01"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self._get(LIST, params).status_code, 400)

    def test_retention_override_per_org(self) -> None:
        Configuration.objects.create(
            organization=self.org,
            key=ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS.name,
            value="5",
        )
        response = self._get(LIST)
        self.assertEqual(
            self._ids(response), [str(self.role.id), str(self.rotate.id)]
        )
        self.assertEqual(response.data["retention_days"], 5)

    def test_from_before_retention_still_hides_expired(self) -> None:
        response = self._get(LIST, {"from": "2000-01-01"})
        self.assertNotIn(str(self.expired.id), self._ids(response))

    # --- permissions -----------------------------------------------------------

    def test_member_is_forbidden(self) -> None:
        views = {"list": LIST, "export": EXPORT, "actions": ACTIONS, "actors": ACTORS}
        for name, view in views.items():
            # A string, not the view: xdist cannot serialise a function.
            with self.subTest(view=name):
                self.assertEqual(self._get(view, user=self.member).status_code, 403)

    def test_platform_key_caller_is_forbidden(self) -> None:
        service_account = make_user("svc@example.com", is_service_account=True)
        key = SimpleNamespace(id=uuid.uuid4(), name="k", permission="full_access")
        response = self._get(LIST, user=service_account, platform_api_key=key)
        self.assertEqual(response.status_code, 403)

    def test_admin_of_another_org_sees_only_that_org(self) -> None:
        other_admin = make_user("other@example.com")
        from tenant_account_v2.models import OrganizationMember

        self.use_org(self.other_org)
        OrganizationMember.objects.create(
            organization=self.other_org, user=other_admin, role="admin"
        )
        response = self._get(LIST, user=other_admin)
        self.assertEqual(self._ids(response), [str(self.foreign.id)])

    # --- export ----------------------------------------------------------------

    def test_export_uses_the_same_filters(self) -> None:
        response = self._get(EXPORT, {"action": "key.rotated"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], CSV_COLUMNS)
        self.assertEqual(len(rows), 2)
        record = dict(zip(CSV_COLUMNS, rows[1], strict=True))
        self.assertEqual(record["action"], "key.rotated")
        self.assertEqual(record["action_label"], "Key rotated")
        self.assertEqual(record["target_name"], "ci-key")

    def test_export_neutralises_formulas(self) -> None:
        self._event(
            "group.created", days_ago=0, target_name="=HYPERLINK(1)", summary="-2+3"
        )
        response = self._get(EXPORT, {"action": "group.created"})
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        record = dict(zip(CSV_COLUMNS, rows[1], strict=True))
        self.assertEqual(record["target_name"], "'=HYPERLINK(1)")
        self.assertEqual(record["summary"], "'-2+3")

    def test_export_over_the_cap_is_413(self) -> None:
        with patch("platform_audit.views.MAX_EXPORT_ROWS", 2):
            response = self._get(EXPORT)
        self.assertEqual(response.status_code, 413)
        # Exactly at the cap is allowed.
        with patch("platform_audit.views.MAX_EXPORT_ROWS", 3):
            self.assertEqual(self._get(EXPORT).status_code, 200)

    # --- actions & actors --------------------------------------------------------

    def test_actions_vocabulary(self) -> None:
        response = self._get(ACTIONS)
        self.assertEqual(response.status_code, 200)
        keys = {row["key"] for row in response.data}
        self.assertTrue(
            {
                "member.role_changed",
                "capability.changed",
                "key.expiry_set",
                "execution.aborted",
            }
            <= keys
        )
        self.assertEqual(set(response.data[0]), {"key", "label", "category"})

    def test_actors_are_one_per_identity_and_skip_the_system_actor(self) -> None:
        self._event("group.created", days_ago=0.5, actor_name="Ada Renamed")
        self._event(
            "group.created", days_ago=0.5, actor=None, actor_type="system", actor_email=""
        )
        response = self._get(ACTORS)
        admins = [row for row in response.data if row["email"] == "admin@example.com"]
        self.assertEqual(len(admins), 1)
        self.assertEqual(admins[0]["name"], "Ada Renamed")
        self.assertNotIn("", [row["email"] for row in response.data])

    def test_actors_include_removed_members_and_skip_expired(self) -> None:
        gone = make_user("gone@example.com")
        self._event("member.removed", days_ago=3, actor=gone, actor_email="gone@example.com")
        self._event("member.removed", days_ago=95, actor_email="ancient@example.com")
        gone.delete()
        response = self._get(ACTORS)
        emails = [row["email"] for row in response.data]
        self.assertEqual(emails, ["admin@example.com", "bot@example.com", "gone@example.com"])
        self.assertIsNone(response.data[2]["id"])

    def test_naive_datetime_is_read_in_server_time(self) -> None:
        query = AuditEventQuerySerializer(data={"from": "2026-01-01T09:00:00"})
        self.assertTrue(query.is_valid(), query.errors)
        self.assertEqual(
            query.validated_data["start"],
            datetime(2026, 1, 1, 9, 0, tzinfo=dt_timezone.utc),
        )

    def test_invalid_from_reports_the_parameter_name(self) -> None:
        for value in ("yesterday", "2999-01-01"):
            with self.subTest(value=value):
                query = AuditEventQuerySerializer(
                    data={"from": value, "to": "2026-01-01"}
                )
                self.assertFalse(query.is_valid())
                self.assertEqual(set(query.errors), {"from"})

    def test_to_at_the_end_of_the_calendar_is_not_a_500(self) -> None:
        for value in ("9999-12-31", "9999-12-31T23:59:59.999999+00:00"):
            with self.subTest(value=value):
                self.assertEqual(self._get(LIST, {"to": value}).status_code, 200)

    def test_ordering_parameter_is_ignored(self) -> None:
        response = self._get(LIST, {"ordering": "occurred_at"})
        self.assertEqual(
            self._ids(response),
            [str(self.role.id), str(self.rotate.id), str(self.group.id)],
        )

    def test_retention_default_out_of_range_is_clamped(self) -> None:
        with patch(
            "platform_audit.retention.Configuration.get_value_by_organization",
            return_value=0,
        ):
            with self.assertLogs("platform_audit.retention", "ERROR"):
                response = self._get(LIST)
        self.assertEqual(response.data["retention_days"], 1)
        self.assertNotIn(str(self.rotate.id), self._ids(response))
