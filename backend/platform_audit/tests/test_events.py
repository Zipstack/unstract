"""One test per recorded event type, through the view that records it.

Identity-provider calls are patched (OSS has no auth plugin); everything else
runs for real so the stored row is what production would store.
"""

import uuid
from unittest.mock import patch

from account_v2.dto import MemberInvitation
from account_v2.models import PlatformKey
from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.db import OperationalError
from django.conf import settings
from adapter_processor_v2.models import AdapterInstance, UserDefaultAdapter
from adapter_processor_v2.views import DefaultAdapterViewSet
from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet
from notification_v2.views import NotificationSettingsView
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.views import PlatformApiKeyViewSet
from platform_settings_v2.views import PlatformKeyViewSet
from tenant_account_v2.group_views import OrganizationGroupViewSet
from tenant_account_v2.invitation_views import InvitationViewSet
from tenant_account_v2.models import GroupMembership, OrganizationGroup, OrganizationMember
from tenant_account_v2.users_view import OrganizationUserViewSet
from tenant_account_v2.views import organization_settings

from platform_audit.models import PlatformAuditEvent
from utils.user_context import UserContext
from platform_audit.tests.base import AuditTestBase, make_user

_CONTROLLER = "account_v2.authentication_controller.AuthenticationController"
_SERVICE = "account_v2.authentication_service.AuthenticationService"


class MemberEventTests(AuditTestBase):
    def _set_role(self, role: str):
        def side_effect(request, org_id, email, new_role):
            OrganizationMember.objects.filter(user__email=email).update(role=role)
            return role

        return side_effect

    def test_role_changed_on_assign(self) -> None:
        view = OrganizationUserViewSet.as_view({"post": "assign_organization_role_to_user"})
        with patch(f"{_CONTROLLER}.add_user_role", side_effect=self._set_role("admin")):
            response = self.call(
                view, "post", data={"email": "member@example.com", "role": "admin"}
            )
        self.assertEqual(response.status_code, 200)
        event = self.only_event(action="member.role_changed")
        self.assert_admin_actor(event)
        self.assertEqual(event.target_type, "member")
        self.assertEqual(event.target_id, str(self.member.id))
        self.assertEqual(event.target_name, "member@example.com")
        self.assertEqual(
            event.changes, {"before": {"role": "user"}, "after": {"role": "admin"}}
        )
        self.assertEqual(event.summary, "user → admin")

    def test_role_changed_on_remove(self) -> None:
        view = OrganizationUserViewSet.as_view(
            {"delete": "remove_organization_role_from_user"}
        )
        OrganizationMember.objects.filter(user=self.member).update(role="admin")
        with patch(f"{_CONTROLLER}.remove_user_role", side_effect=self._set_role("user")):
            self.call(view, "delete", data={"email": "member@example.com", "role": "admin"})
        event = self.only_event(action="member.role_changed")
        self.assertEqual(
            event.changes, {"before": {"role": "admin"}, "after": {"role": "user"}}
        )

    def test_role_change_with_unknown_previous_role_omits_before(self) -> None:
        view = OrganizationUserViewSet.as_view({"post": "assign_organization_role_to_user"})
        with (
            patch(
                "tenant_account_v2.users_view.OrganizationMemberService.get_user_by_email",
                side_effect=RuntimeError("db"),
            ),
            patch(f"{_CONTROLLER}.add_user_role", return_value="admin"),
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR"):
                self.call(view, "post", data={"email": "member@example.com", "role": "admin"})
        event = self.only_event(action="member.role_changed")
        self.assertEqual(event.changes, {"after": {"role": "admin"}})
        self.assertEqual(event.summary, "role → admin (previous value unavailable)")

    def test_failed_or_unchanged_role_records_nothing(self) -> None:
        view = OrganizationUserViewSet.as_view({"post": "assign_organization_role_to_user"})
        with patch(f"{_CONTROLLER}.add_user_role", return_value=None):
            response = self.call(
                view, "post", data={"email": "member@example.com", "role": "admin"}
            )
        self.assertEqual(response.status_code, 400)
        with patch(f"{_CONTROLLER}.add_user_role", return_value="user"):
            self.call(view, "post", data={"email": "member@example.com", "role": "user"})
        self.assertEqual(self.events(), [])

    def _invite(self, users: list[dict], idp_results: list) -> object:
        """POST users/invite/ through the real controller loop, with the
        identity provider's per-user call answering ``idp_results`` in order.
        """
        view = OrganizationUserViewSet.as_view({"post": "invite_user"})
        with (
            patch(f"{_SERVICE}.is_organization_admin", return_value=True),
            patch(f"{_SERVICE}.invite_user", side_effect=idp_results),
        ):
            return self.call(view, "post", data={"users": users})

    def test_invited_records_only_successful_invites(self) -> None:
        # member@ is already a member, so the IdP is never asked about them.
        response = self._invite(
            [
                {"email": "new@example.com", "role": "user"},
                {"email": "member@example.com", "role": "user"},
                {"email": "refused@example.com", "role": "user"},
            ],
            [True, False],
        )
        self.assertEqual(response.status_code, 200)
        event = self.only_event(action="member.invited")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("invitation", "new@example.com", "new@example.com"),
        )
        self.assertEqual(event.changes, {"after": {"role": "user"}})
        self.assertEqual(event.summary, "as user")

    def test_invites_sent_before_a_failing_one_are_still_recorded(self) -> None:
        # The IdP raises on the third: the first two invitations were sent.
        response = self._invite(
            [
                {"email": "a@example.com", "role": "user"},
                {"email": "b@example.com", "role": "admin"},
                {"email": "c@example.com", "role": "user"},
            ],
            [True, True, RuntimeError("idp 429")],
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            sorted(
                (e.target_name, e.changes["after"]["role"])
                for e in self.events(action="member.invited")
            ),
            [("a@example.com", "user"), ("b@example.com", "admin")],
        )

    def test_a_failing_organisation_lookup_does_not_stop_invites(self) -> None:
        # Only the audit side's lookups fail: the view's and the recorder's.
        with (
            patch("tenant_account_v2.users_view.UserContext") as view_context,
            patch("platform_audit.recorder.UserContext") as recorder_context,
        ):
            view_context.get_organization.side_effect = OperationalError("db")
            recorder_context.get_organization.side_effect = OperationalError("db")
            response = self._invite(
                [{"email": "new@example.com", "role": "user"}], [True]
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.events(), [])

    def test_each_invite_records_its_own_role(self) -> None:
        self._invite(
            [
                {"email": "twice@example.com", "role": "admin"},
                {"email": "twice@example.com", "role": "user"},
            ],
            [True, True],
        )
        self.assertEqual(
            sorted(e.summary for e in self.events(action="member.invited")),
            ["as admin", "as user"],
        )

    def test_removed_records_the_previous_role(self) -> None:
        view = OrganizationUserViewSet.as_view({"delete": "remove_members_from_organization"})
        with patch(f"{_CONTROLLER}.remove_users_from_organization", return_value=True):
            response = self.call(view, "delete", data={"emails": ["member@example.com"]})
        self.assertEqual(response.status_code, 200)
        event = self.only_event(action="member.removed")
        self.assert_admin_actor(event)
        self.assertEqual(event.target_id, str(self.member.id))
        self.assertEqual(event.target_name, "member@example.com")
        self.assertEqual(event.changes, {"before": {"role": "user"}})
        self.assertEqual(event.summary, "was user")

    def test_removal_with_an_unreadable_snapshot_is_still_recorded(self) -> None:
        view = OrganizationUserViewSet.as_view({"delete": "remove_members_from_organization"})
        with (
            patch(
                "tenant_account_v2.users_view.OrganizationMemberService.get_user_by_email",
                side_effect=RuntimeError("db"),
            ),
            patch(f"{_CONTROLLER}.remove_users_from_organization", return_value=True),
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR"):
                self.call(view, "delete", data={"emails": ["Member@Example.com"]})
        event = self.only_event(action="member.removed")
        self.assertEqual(
            (event.target_id, event.target_name, event.changes),
            ("", "member@example.com", {}),
        )
        self.assertEqual(
            event.summary, "membership not confirmed (previous value unavailable)"
        )

    def test_a_failed_removal_records_nothing(self) -> None:
        view = OrganizationUserViewSet.as_view({"delete": "remove_members_from_organization"})
        with patch(f"{_CONTROLLER}.remove_users_from_organization", return_value=False):
            response = self.call(view, "delete", data={"emails": ["member@example.com"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.events(), [])

    def test_a_non_member_in_the_list_is_skipped_not_fatal(self) -> None:
        view = OrganizationUserViewSet.as_view({"delete": "remove_members_from_organization"})
        with patch(f"{_CONTROLLER}.remove_users_from_organization", return_value=True):
            self.call(
                view,
                "delete",
                data={"emails": ["stranger@example.com", "member@example.com"]},
            )
        event = self.only_event(action="member.removed")
        self.assertEqual(event.target_name, "member@example.com")

    def test_invitation_revoked_resolves_the_email(self) -> None:
        view = InvitationViewSet.as_view({"delete": "delete_invitation"})
        invitation = MemberInvitation(id="inv-1", email="new@example.com", roles=["user"])
        with (
            patch(f"{_CONTROLLER}.get_user_invitations", return_value=[invitation]),
            patch(f"{_CONTROLLER}.delete_user_invitation", return_value=True),
        ):
            response = self.call(view, "delete", id="inv-1")
        self.assertEqual(response.status_code, 204)
        event = self.only_event(action="invitation.revoked")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("invitation", "inv-1", "new@example.com"),
        )

    def test_a_failed_revoke_records_nothing(self) -> None:
        view = InvitationViewSet.as_view({"delete": "delete_invitation"})
        invitation = MemberInvitation(id="inv-1", email="new@example.com", roles=["user"])
        with (
            patch(f"{_CONTROLLER}.get_user_invitations", return_value=[invitation]),
            patch(f"{_CONTROLLER}.delete_user_invitation", return_value=False),
        ):
            response = self.call(view, "delete", id="inv-1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.events(), [])

    def test_invitation_revoked_falls_back_to_the_id(self) -> None:
        view = InvitationViewSet.as_view({"delete": "delete_invitation"})
        with (
            patch(f"{_CONTROLLER}.get_user_invitations", side_effect=RuntimeError("idp")),
            patch(f"{_CONTROLLER}.delete_user_invitation", return_value=True),
        ):
            response = self.call(view, "delete", id="inv-1")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.only_event().target_name, "inv-1")


class GroupEventTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        for target in (
            "tenant_account_v2.sharing_helpers.is_org_admin",
            "tenant_account_v2.group_views.notify_group_membership_changed",
        ):
            patcher = patch(target, return_value=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.group = OrganizationGroup.objects.create(
            organization=self.org, name="Team", description="d"
        )

    def test_created(self) -> None:
        view = OrganizationGroupViewSet.as_view({"post": "create"})
        response = self.call(view, "post", data={"name": "Ops", "description": "x"})
        self.assertEqual(response.status_code, 201)
        event = self.only_event(action="group.created")
        self.assert_admin_actor(event)
        group = OrganizationGroup.objects.get(name="Ops")
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("group", str(group.id), "Ops"),
        )
        self.assertEqual(event.changes, {"after": {"name": "Ops", "description": "x"}})

    def test_changed_records_the_diff(self) -> None:
        view = OrganizationGroupViewSet.as_view({"patch": "partial_update"})
        self.call(view, "patch", data={"name": "Team 2"}, pk=self.group.pk)
        event = self.only_event(action="group.changed")
        self.assert_admin_actor(event)
        self.assertEqual(event.target_name, "Team 2")
        self.assertEqual(
            event.changes, {"before": {"name": "Team"}, "after": {"name": "Team 2"}}
        )
        self.assertEqual(event.summary, "renamed from Team")

    def test_unchanged_update_records_nothing(self) -> None:
        view = OrganizationGroupViewSet.as_view({"patch": "partial_update"})
        self.call(view, "patch", data={"name": "Team"}, pk=self.group.pk)
        self.assertEqual(self.events(), [])

    def test_deleted(self) -> None:
        view = OrganizationGroupViewSet.as_view({"delete": "destroy"})
        group_id = self.group.pk
        response = self.call(view, "delete", pk=group_id)
        self.assertEqual(response.status_code, 204)
        event = self.only_event(action="group.deleted")
        self.assert_admin_actor(event)
        self.assertEqual((event.target_id, event.target_name), (str(group_id), "Team"))
        self.assertEqual(event.changes, {"before": {"name": "Team", "description": "d"}})

    def test_member_added_and_removed(self) -> None:
        add = OrganizationGroupViewSet.as_view({"post": "members"})
        response = self.call(
            add, "post", data={"user_ids": [self.member.id]}, pk=self.group.pk
        )
        self.assertEqual(response.status_code, 201, response.data)
        added = self.only_event(action="group.member_added")
        self.assert_admin_actor(added)
        self.assertEqual(
            (added.target_type, added.target_id, added.target_name, added.summary),
            ("group", str(self.group.pk), "Team", "member@example.com"),
        )
        self.assertEqual(
            added.metadata, {"user_id": self.member.id, "email": "member@example.com"}
        )

        # Bulk adds resolve the organisation once, not once per event: adding
        # two users costs no more lookups than adding one.
        lookups = []
        for emails in (["one@example.com"], ["two@example.com", "three@example.com"]):
            users = [make_user(email) for email in emails]
            for user in users:
                OrganizationMember.objects.create(
                    organization=self.org, user=user, role="user"
                )
            with patch(
                "utils.user_context.UserContext.get_organization",
                wraps=UserContext.get_organization,
            ) as spy:
                self.call(
                    add, "post", data={"user_ids": [u.id for u in users]}, pk=self.group.pk
                )
            lookups.append(spy.call_count)
        self.assertEqual(lookups[0], lookups[1])
        self.assertEqual(len(self.events(action="group.member_added")), 4)

        remove = OrganizationGroupViewSet.as_view({"delete": "remove_member"})
        self.call(remove, "delete", pk=self.group.pk, user_id=str(self.member.id))
        removed = self.only_event(action="group.member_removed")
        self.assertEqual(removed.summary, "member@example.com")
        self.assertFalse(
            GroupMembership.objects.filter(group=self.group, user=self.member).exists()
        )


class PlatformApiKeyEventTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = PlatformApiKey.objects.create(
            name="ci", description="d", organization=self.org
        )

    def test_created(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"post": "create"})
        response = self.call(
            view, "post", data={"name": "etl", "description": "x", "permission": "read"}
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = self.only_event(action="key.created")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("platform_api_key", response.data["id"], "etl"),
        )
        self.assertEqual(
            event.changes,
            {"after": {"description": "x", "is_active": True, "permission": "read"}},
        )
        self.assertNotIn(str(response.data["key"]), str(event.changes))

    def test_disabled_then_enabled(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"patch": "partial_update"})
        self.call(view, "patch", data={"is_active": False}, pk=self.key.pk)
        self.call(view, "patch", data={"is_active": True}, pk=self.key.pk)
        disabled, enabled = self.events()
        self.assertEqual(disabled.action, "key.disabled")
        self.assertEqual(
            disabled.changes,
            {"before": {"is_active": True}, "after": {"is_active": False}},
        )
        self.assertEqual(enabled.action, "key.enabled")
        self.assert_admin_actor(enabled)

    def test_changed_records_other_fields(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"patch": "partial_update"})
        self.call(view, "patch", data={"permission": "full_access"}, pk=self.key.pk)
        event = self.only_event(action="key.changed")
        self.assertEqual(
            event.changes,
            {"before": {"permission": "read_write"}, "after": {"permission": "full_access"}},
        )
        self.assertEqual(event.summary, "changed permission")

    def test_rotated_by_a_full_access_key(self) -> None:
        service_account = make_user("svc@example.com", is_service_account=True)
        caller = PlatformApiKey.objects.create(
            name="admin-bot",
            description="d",
            organization=self.org,
            permission=ApiKeyPermission.FULL_ACCESS,
            api_user=service_account,
        )
        view = PlatformApiKeyViewSet.as_view({"post": "rotate"})
        response = self.call(
            view, "post", user=service_account, platform_api_key=caller, pk=self.key.pk
        )
        self.assertEqual(response.status_code, 200, response.data)
        event = self.only_event(action="key.rotated")
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("platform_api_key", str(self.key.id), "ci"),
        )
        self.assertEqual(event.actor, service_account)
        self.assertEqual(event.actor_type, "api_key")
        self.assertEqual(event.actor_key_id, str(caller.id))
        self.assertEqual(event.actor_key_name, "admin-bot")

    def test_revoked(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"delete": "destroy"})
        key_id = self.key.id
        response = self.call(view, "delete", pk=key_id)
        self.assertEqual(response.status_code, 204)
        event = self.only_event(action="key.revoked")
        self.assert_admin_actor(event)
        self.assertEqual((event.target_id, event.target_name), (str(key_id), "ci"))

    def test_unreadable_before_records_a_snapshot_and_files_the_flip(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"patch": "partial_update"})
        cases = (
            # (request body, expected flip action or None)
            ({"is_active": False, "description": "new"}, "key.disabled"),
            ({"is_active": True}, "key.enabled"),
            ({"description": "new"}, None),
        )
        for body, flip in cases:
            with self.subTest(body=str(body)):
                PlatformAuditEvent.objects.purge(PlatformAuditEvent.objects.all())
                after = {
                    "description": body.get("description", "d"),
                    "is_active": body.get("is_active", True),
                    "permission": "read_write",
                }
                with patch("platform_api.views._key_fields", side_effect=[None, after]):
                    self.call(view, "patch", data=body, pk=self.key.pk)
                if flip:
                    event = self.only_event(action=flip)
                    self.assertEqual(
                        event.changes, {"after": {"is_active": after["is_active"]}}
                    )
                    self.assertEqual(event.summary, "(previous value unavailable)")
                else:
                    self.assertEqual(self.events(action="key.enabled"), [])
                    self.assertEqual(self.events(action="key.disabled"), [])
                if set(body) == {"is_active"}:
                    # A flip-only request changed nothing else.
                    self.assertEqual(self.events(action="key.changed"), [])
                    continue
                snapshot = {k: v for k, v in after.items() if k != "is_active"}
                changed = self.only_event(action="key.changed")
                self.assertEqual(changed.changes, {"after": snapshot})
                self.assertEqual(
                    changed.summary, "current values (previous value unavailable)"
                )

    def test_a_failing_audit_write_does_not_change_the_response(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"post": "rotate"})
        with patch.object(
            PlatformAuditEvent.objects, "create", side_effect=RuntimeError("db down")
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR"):
                response = self.call(view, "post", pk=self.key.pk)
        self.assertEqual(response.status_code, 200)
        self.key.refresh_from_db()
        self.assertEqual(str(self.key.key), str(response.data["key"]))


class GlobalApiDeploymentKeyEventTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = GlobalApiDeploymentKey.objects.create(
            name="g", description="d", organization=self.org, allow_all_deployments=True
        )

    def test_created(self) -> None:
        view = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
        response = self.call(
            view,
            "post",
            data={"name": "g2", "description": "x", "allow_all_deployments": True},
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = self.only_event(action="key.created")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_name),
            ("global_api_deployment_key", "g2"),
        )
        self.assertEqual(
            event.changes,
            {
                "after": {
                    "description": "x",
                    "is_active": True,
                    "allow_all_deployments": True,
                    "api_deployments": [],
                }
            },
        )

    def test_disabled_rotated_revoked(self) -> None:
        update = GlobalApiDeploymentKeyViewSet.as_view({"patch": "partial_update"})
        rotate = GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"})
        destroy = GlobalApiDeploymentKeyViewSet.as_view({"delete": "destroy"})
        key_id = self.key.id
        self.call(update, "patch", data={"is_active": False}, pk=key_id)
        self.call(update, "patch", data={"description": "new"}, pk=key_id)
        self.call(rotate, "post", pk=key_id)
        response = self.call(destroy, "delete", pk=key_id)
        self.assertEqual(response.status_code, 204)
        events = self.events()
        self.assertEqual(
            [e.action for e in events],
            ["key.disabled", "key.changed", "key.rotated", "key.revoked"],
        )
        self.assertEqual(
            events[1].changes,
            {"before": {"description": "d"}, "after": {"description": "new"}},
        )
        for event in events:
            self.assert_admin_actor(event)
            self.assertEqual(
                (event.target_type, event.target_id, event.target_name),
                ("global_api_deployment_key", str(key_id), "g"),
            )


class PlatformKeyEventTests(AuditTestBase):
    """The legacy platform keys under Settings > Platform."""

    def _key(self, name: str, is_active: bool) -> PlatformKey:
        return PlatformKey.objects.create(
            key_name=name, is_active=is_active, organization=self.org
        )

    def test_created(self) -> None:
        view = PlatformKeyViewSet.as_view({"post": "create"})
        response = self.call(view, "post", data={"key_name": "k1", "is_active": False})
        self.assertEqual(response.status_code, 201, response.data)
        event = self.only_event(action="key.created")
        self.assert_admin_actor(event)
        key = PlatformKey.objects.get(key_name="k1")
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("platform_key", str(key.id), "k1"),
        )
        self.assertEqual(event.changes, {"after": {"is_active": False}})

    def test_created_inactive_from_a_string_is_recorded_inactive(self) -> None:
        view = PlatformKeyViewSet.as_view({"post": "create"})
        response = self.call(view, "post", data={"key_name": "k2", "is_active": "False"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(PlatformKey.objects.get(key_name="k2").is_active)
        event = self.only_event(action="key.created")
        self.assertEqual(event.changes, {"after": {"is_active": False}})

    def test_activate_records_the_keys_it_deactivates(self) -> None:
        old = self._key("old", is_active=True)
        new = self._key("new", is_active=False)
        view = PlatformKeyViewSet.as_view({"post": "toggle_platform_key"})
        self.call(view, "post", data={"action": "ACTIVATE"}, pk=new.pk)
        enabled = self.only_event(action="key.enabled")
        self.assertEqual(enabled.target_id, str(new.id))
        disabled = self.only_event(action="key.disabled")
        self.assertEqual(disabled.target_id, str(old.id))
        self.assertEqual(disabled.summary, "deactivated when new was activated")

    def test_deactivate(self) -> None:
        key = self._key("k", is_active=True)
        view = PlatformKeyViewSet.as_view({"post": "toggle_platform_key"})
        self.call(view, "post", data={"action": "DEACTIVATE"}, pk=key.pk)
        event = self.only_event()
        self.assertEqual((event.action, event.target_id), ("key.disabled", str(key.id)))
        # Deactivating an already inactive key is not a change.
        self.call(view, "post", data={"action": "DEACTIVATE"}, pk=key.pk)
        self.assertEqual(len(self.events()), 1)

    def test_reactivating_an_active_key_records_the_keys_it_deactivates(self) -> None:
        other = self._key("other", is_active=True)
        key = self._key("k", is_active=True)
        view = PlatformKeyViewSet.as_view({"post": "toggle_platform_key"})
        self.call(view, "post", data={"action": "ACTIVATE"}, pk=key.pk)
        event = self.only_event()
        self.assertEqual((event.action, event.target_id), ("key.disabled", str(other.id)))

    def test_refresh_and_destroy(self) -> None:
        key = self._key("k", is_active=False)
        refresh = PlatformKeyViewSet.as_view({"put": "refresh"})
        destroy = PlatformKeyViewSet.as_view({"delete": "destroy"})
        self.call(refresh, "put", data={"id": str(key.id)})
        self.call(destroy, "delete", pk=key.pk)
        rotated, revoked = self.events()
        self.assertEqual(
            (rotated.action, rotated.target_id, rotated.target_name),
            ("key.rotated", str(key.id), "k"),
        )
        self.assertEqual(
            (revoked.action, revoked.target_id, revoked.target_name),
            ("key.revoked", str(key.id), "k"),
        )


class DefaultProfileEventTests(AuditTestBase):
    def _adapter(self, name: str, adapter_type: str) -> AdapterInstance:
        return AdapterInstance.objects.create(
            adapter_name=name,
            adapter_id=f"{name}|{uuid.uuid4()}",
            adapter_type=adapter_type,
            adapter_metadata={},
            organization=self.org,
            created_by=self.admin,
        )

    def test_changed_records_names_per_slot(self) -> None:
        old_llm = self._adapter("sonnet", "LLM")
        new_llm = self._adapter("gpt", "LLM")
        embedding = self._adapter("ada", "EMBEDDING")
        UserDefaultAdapter.objects.create(
            organization_member=OrganizationMember.objects.get(user=self.admin),
            default_llm_adapter=old_llm,
            default_embedding_adapter=embedding,
        )
        view = DefaultAdapterViewSet.as_view({"post": "configure_default_triad"})
        response = self.call(
            view,
            "post",
            data={"llm_default": str(new_llm.id), "embedding_default": str(embedding.id)},
        )
        self.assertEqual(response.status_code, 200)
        event = self.only_event(action="default_profile.changed")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("default_profile", str(self.admin.id), self.admin.email),
        )
        self.assertEqual(
            event.changes, {"before": {"llm": "sonnet"}, "after": {"llm": "gpt"}}
        )
        self.assertEqual(event.summary, "llm: sonnet → gpt")

    def test_unreadable_previous_defaults_record_the_current_ones(self) -> None:
        view = DefaultAdapterViewSet.as_view({"post": "configure_default_triad"})
        now = {"llm": "gpt", "embedding": None, "vector_db": None, "x2text": None}
        with patch(
            "adapter_processor_v2.views._default_adapter_names", side_effect=[None, now]
        ):
            with patch("adapter_processor_v2.views.AdapterProcessor.set_default_triad"):
                self.call(view, "post", data={})
        event = self.only_event(action="default_profile.changed")
        self.assertEqual(event.changes, {"after": now})
        self.assertEqual(
            event.summary,
            "llm → gpt; embedding → none; vector_db → none; x2text → none "
            "(previous value unavailable)",
        )


class PlatformSettingEventTests(AuditTestBase):
    def test_organization_setting_changed(self) -> None:
        """Its flags are the storage of two capabilities (UN-4399), so a change
        is recorded once, as the capability changing."""
        response = self.call(
            organization_settings,
            "patch",
            data={"restrict_llm_adapter_creation": True},
        )
        self.assertEqual(response.status_code, 200)
        event = self.only_event(action="capability.changed")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("capability", "create_llm_adapters", "Create LLM adapters"),
        )
        self.assertEqual(
            event.changes,
            {"before": {"setting": "any_member"}, "after": {"setting": "admins_only"}},
        )
        # Re-sending the same value is not a change.
        self.call(
            organization_settings, "patch", data={"restrict_llm_adapter_creation": True}
        )
        self.assertEqual(len(self.events()), 1)

    def test_notification_interval_changed(self) -> None:
        view = NotificationSettingsView.as_view()
        response = self.call(view, "patch", data={"club_interval_seconds": 600})
        self.assertEqual(response.status_code, 200, response.data)
        event = self.only_event(action="platform_setting.changed")
        self.assert_admin_actor(event)
        self.assertEqual(event.target_id, "club_interval_seconds")
        self.assertEqual(
            event.changes,
            {
                "before": {"club_interval_seconds": settings.NOTIFICATION_CLUB_INTERVAL},
                "after": {"club_interval_seconds": 600},
            },
        )
        # Re-sending the same value is not a change.
        self.call(view, "patch", data={"club_interval_seconds": 600})
        self.assertEqual(len(self.events()), 1)

    def test_an_existing_override_is_the_before_value(self) -> None:
        Configuration.objects.create(
            organization=self.org,
            key=ConfigKey.NOTIFICATION_CLUB_INTERVAL.name,
            value="300",
        )
        view = NotificationSettingsView.as_view()
        self.call(view, "patch", data={"club_interval_seconds": 600})
        event = self.only_event(action="platform_setting.changed")
        self.assertEqual(
            event.changes,
            {
                "before": {"club_interval_seconds": 300},
                "after": {"club_interval_seconds": 600},
            },
        )

    def test_unreadable_before_value_is_left_out(self) -> None:
        # A failed query: the lenient lookup would return the default here.
        view = NotificationSettingsView.as_view()
        with patch(
            "notification_v2.views.Configuration.objects.filter",
            side_effect=OperationalError("timeout"),
        ):
            with self.assertLogs("platform_audit.recorder", "ERROR"):
                self.call(view, "patch", data={"club_interval_seconds": 600})
        event = self.only_event(action="platform_setting.changed")
        self.assertEqual(event.changes, {"after": {"club_interval_seconds": 600}})
        self.assertEqual(
            event.summary, "club_interval_seconds → 600 (previous value unavailable)"
        )
