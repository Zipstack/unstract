import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection, transaction
from django.utils import timezone

from platform_audit.actions import Action, TargetType
from platform_audit.models import PlatformAuditEvent
from platform_audit.recorder import _write, best_effort, record_platform_event
from platform_audit.tests.base import AuditTestBase, make_user


class RecorderTests(AuditTestBase):
    def _record(self, **kwargs):
        defaults = {
            "action": Action.GROUP_CREATED,
            "target_type": TargetType.GROUP,
            "target_id": 7,
            "target_name": "Team",
            "actor": self.admin,
        }
        with self.captureOnCommitCallbacks(execute=True):
            record_platform_event(**{**defaults, **kwargs})

    def test_stores_every_field(self) -> None:
        request = SimpleNamespace(user=self.admin, id="req-123")
        self._record(
            actor=None,
            request=request,
            changes={"before": {"name": "A"}, "after": {"name": "B"}},
            summary="renamed",
            metadata={"x": uuid.UUID(int=1)},
        )
        event = self.only_event()
        self.assert_admin_actor(event)
        self.assertEqual(event.action, "group.created")
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("group", "7", "Team"),
        )
        self.assertEqual(event.changes, {"before": {"name": "A"}, "after": {"name": "B"}})
        self.assertEqual(event.summary, "renamed")
        self.assertEqual(event.metadata, {"x": str(uuid.UUID(int=1))})

    def test_platform_key_caller_is_recorded_as_the_key(self) -> None:
        service_account = make_user("svc@example.com", is_service_account=True)
        key = SimpleNamespace(id=uuid.UUID(int=5), name="ci-bot")
        request = SimpleNamespace(user=service_account, platform_api_key=key)
        self._record(actor=None, request=request)
        event = self.only_event()
        self.assertEqual(event.actor, service_account)
        self.assertEqual(event.actor_type, "api_key")
        self.assertEqual(event.actor_email, "svc@example.com")
        self.assertEqual(event.actor_key_id, str(key.id))
        self.assertEqual(event.actor_key_name, "ci-bot")

    def test_no_actor_is_system(self) -> None:
        self._record(actor=None)
        event = self.only_event()
        self.assertEqual(event.actor_type, "system")
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_email, "")

    def test_explicit_organization_wins_over_context(self) -> None:
        self._record(organization=self.other_org)
        self.assertEqual(self.only_event().organization, self.other_org)

    def test_unregistered_action_is_logged_not_stored(self) -> None:
        with self.assertLogs("platform_audit.recorder", "ERROR"):
            self._record(action="nope.unknown")
        self.assertEqual(self.events(), [])

    def test_missing_organization_is_logged_not_stored(self) -> None:
        with patch(
            "platform_audit.recorder.UserContext.get_organization", return_value=None
        ):
            with self.assertLogs("platform_audit.recorder", "WARNING"):
                self._record()
        self.assertEqual(self.events(), [])

    def test_failing_write_is_logged_and_swallowed(self) -> None:
        with patch.object(
            PlatformAuditEvent.objects, "create", side_effect=RuntimeError("db down")
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
                self._record()  # must not raise
        self.assertIn("failed to write", logs.output[0])
        self.assertEqual(self.events(), [])

    def test_failure_while_resolving_is_logged_and_swallowed(self) -> None:
        with patch(
            "platform_audit.recorder._resolve_actor", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR"):
                self._record()
        self.assertEqual(self.events(), [])

    def test_nothing_is_recorded_when_the_change_rolls_back(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    record_platform_event(
                        action=Action.GROUP_DELETED,
                        target_type=TargetType.GROUP,
                        target_id=1,
                        actor=self.admin,
                    )
                    raise RuntimeError("change failed")
            except RuntimeError:
                pass
        self.assertEqual(self.events(), [])

    def test_changes_keep_only_before_and_after_and_drop_unknown_sides(self) -> None:
        with self.assertLogs("platform_audit.recorder", "WARNING"):
            self._record(changes={"before": None, "after": {"a": 1}, "old": 2})
        self.assertEqual(self.only_event().changes, {"after": {"a": 1}})

    def test_write_failure_log_names_the_change(self) -> None:
        with patch.object(
            PlatformAuditEvent.objects, "create", side_effect=RuntimeError("db down")
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
                self._record()
        self.assertIn("org=org-a target=group:7", logs.output[0])

    def test_write_failure_log_redacts_an_email_target(self) -> None:
        with patch.object(
            PlatformAuditEvent.objects, "create", side_effect=RuntimeError("db down")
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
                self._record(
                    action=Action.MEMBER_INVITED,
                    target_type=TargetType.INVITATION,
                    target_id="invitee@example.com",
                )
        self.assertNotIn("invitee@example.com", logs.output[0])
        self.assertIn("target=invitation:<redacted>", logs.output[0])
        self.assertIn(f"actor=user:{self.admin.pk}", logs.output[0])
        self.assertNotIn("admin@example.com", logs.output[0])

    def test_a_real_database_error_logs_sqlstate_not_the_row(self) -> None:
        """Postgres echoes a rejected row ("Failing row contains ...")."""
        fields = {
            "organization": None,  # NOT NULL: 23502
            "occurred_at": timezone.now(),
            "action": Action.MEMBER_INVITED,
            "target_type": TargetType.INVITATION,
            "target_id": "invitee@example.com",
            "actor_type": "system",
            "summary": "as invitee@example.com",
        }
        with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
            _write(fields)
        output = "\n".join(logs.output)
        self.assertIn("IntegrityError, sqlstate=23502", output)
        self.assertNotIn("invitee@example.com", output)
        self.assertNotIn("Failing row", output)

    def test_a_non_database_error_logs_where_it_was_raised(self) -> None:
        with patch.object(
            PlatformAuditEvent.objects,
            "create",
            side_effect=TypeError("Object of type set is not JSON serializable"),
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
                self._record()
        output = "\n".join(logs.output)
        self.assertIn("TypeError, sqlstate=None, at ", output)
        self.assertIn("recorder.py:", output)
        self.assertNotIn("JSON serializable", output)

    def test_helper_failures_leave_out_the_message_too(self) -> None:
        @best_effort
        def lookup() -> None:
            raise RuntimeError("no member invitee@example.com")

        with self.assertLogs("platform_audit.recorder", "ERROR") as logs:
            lookup()
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("invitee@example.com", logs.output[0])

    def test_long_values_are_clipped_to_the_column(self) -> None:
        self._record(target_name="x" * 400)
        self.assertEqual(len(self.only_event().target_name), 255)


class ImmutabilityTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.event = PlatformAuditEvent.objects.create(
            organization=self.org,
            actor_type="system",
            action=Action.GROUP_CREATED,
            target_type=TargetType.GROUP,
        )

    def test_saving_an_existing_event_is_refused(self) -> None:
        self.event.summary = "edited"
        with self.assertRaises(PermissionError):
            self.event.save()

    def test_deleting_an_event_is_refused(self) -> None:
        with self.assertRaises(PermissionError):
            self.event.delete()

    def test_queryset_update_and_delete_are_refused(self) -> None:
        with self.assertRaises(PermissionError):
            PlatformAuditEvent.objects.filter(pk=self.event.pk).update(summary="x")
        with self.assertRaises(PermissionError):
            PlatformAuditEvent.objects.filter(pk=self.event.pk).delete()

    def test_purge_deletes(self) -> None:
        deleted = PlatformAuditEvent.objects.purge(
            PlatformAuditEvent.objects.filter(pk=self.event.pk)
        )
        self.assertEqual(deleted, 1)
        self.assertFalse(PlatformAuditEvent.objects.exists())


class BestEffortTests(AuditTestBase):
    def test_returns_none_and_logs_on_error(self) -> None:
        @best_effort
        def broken() -> int:
            raise ValueError("nope")

        with self.assertLogs("platform_audit.recorder", "ERROR"):
            self.assertIsNone(broken())

    def test_passes_the_result_through(self) -> None:
        self.assertEqual(best_effort(lambda: 3)(), 3)


class BestEffortSavepointTests(AuditTestBase):
    """TestCase runs inside a transaction, like a request under ATOMIC_REQUESTS."""

    def test_a_failed_query_does_not_abort_the_outer_transaction(self) -> None:
        @best_effort
        def broken_lookup() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0")

        with self.assertLogs("platform_audit.recorder", "ERROR"):
            self.assertIsNone(broken_lookup())
        # Without a savepoint Postgres refuses every further statement here.
        self.assertFalse(PlatformAuditEvent.objects.exists())

    def test_outside_a_transaction_no_transaction_is_opened(self) -> None:
        """Outside ATOMIC_REQUESTS a helper must not defer its on_commit writes."""

        @best_effort
        def helper() -> int:
            return 5

        not_atomic = type("Conn", (), {"in_atomic_block": False})()
        with (
            patch(
                "platform_audit.recorder.transaction.get_connection",
                return_value=not_atomic,
            ),
            patch(
                "platform_audit.recorder.transaction.atomic",
                side_effect=AssertionError("opened a transaction"),
            ),
        ):
            self.assertEqual(helper(), 5)
