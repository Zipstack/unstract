"""Unit tests for the group-notification enqueue side (UN-3494 / mfbt UNS-848).

``share_notifications`` runs inside the user's share request: it builds the task
payload and hands it to the transport. Nothing here touches the ORM or sends
mail, so the module is patched at its three seams — ``kind_for_instance``,
``_feature_enabled`` and ``_dispatch`` — and these run in the rig's unit tier
with no Postgres. The transport itself is covered by ``pg_queue.tests`` and
``workflow_manager.workflow_v2.tests.test_transport``; the delivery side by
``ResourceShareNotificationTests`` in ``tenant_account_v2.tests``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import tenant_account_v2.share_notifications as sn

_ACTOR = SimpleNamespace(pk=7)
_RESOURCE = SimpleNamespace(
    pk="wf-1", organization=SimpleNamespace(organization_id="org-a")
)


def _group(pk: int) -> SimpleNamespace:
    return SimpleNamespace(pk=pk)


@contextmanager
def _seams(*, enabled: bool = True, dispatch_raises: Exception | None = None):
    """Patch the module's three outbound seams; yield the flag + dispatch mocks."""
    with (
        patch.object(sn, "kind_for_instance", return_value="workflow"),
        patch.object(sn, "_feature_enabled", return_value=enabled) as flag,
        patch.object(sn, "_dispatch", side_effect=dispatch_raises) as dispatch,
    ):
        yield flag, dispatch


class TestNotifyResourceGroupShareChanged:
    def test_grant_dispatches_shared_payload_without_timestamp(self):
        with _seams() as (_, dispatch):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[_group(5), _group(2)], removed=[], actor=_ACTOR
            )
        dispatch.assert_called_once()
        call = dispatch.call_args.kwargs
        assert call["task_name"] == sn.NOTIFY_RESOURCE_SHARED_TASK
        assert call["organization_id"] == "org-a"
        assert call["entity_id"] == "wf-1"
        assert call["kwargs"] == {
            "group_ids": [2, 5],  # sorted, so the payload is stable
            "actor_id": 7,
            "resource_kind": "workflow",
            "resource_id": "wf-1",
            "share_action": "shared",
            "organization_id": "org-a",
        }
        # A grant carries no cutoff — the delivery side mails every live member.
        assert "revoked_at" not in call["kwargs"]

    def test_revoke_dispatches_revoked_payload_with_timestamp(self):
        with _seams() as (_, dispatch):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[], removed=[_group(3)], actor=_ACTOR
            )
        payload = dispatch.call_args.kwargs["kwargs"]
        assert payload["share_action"] == "revoked"
        assert payload["group_ids"] == [3]
        # ISO-8601 string, not a datetime — the payload is JSON-serialized.
        datetime.fromisoformat(payload["revoked_at"])

    def test_revoked_at_is_stamped_before_the_flipt_round_trip(self):
        # Regression (PR #2224): the stamp used to sit below ``_feature_enabled``,
        # whose Flipt call is a network round-trip. Someone joining the group
        # inside that window is mailed a revocation for access never held.
        clock = [datetime(2026, 1, 1, 12, 0, tzinfo=UTC)]

        def _flipt(_org: str) -> bool:
            clock[0] += timedelta(seconds=5)  # stand-in for the Flipt round-trip
            return True

        with (
            patch.object(sn.timezone, "now", side_effect=lambda: clock[0]),
            patch.object(sn, "kind_for_instance", return_value="workflow"),
            patch.object(sn, "_feature_enabled", side_effect=_flipt),
            patch.object(sn, "_dispatch") as dispatch,
        ):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[], removed=[_group(3)], actor=_ACTOR
            )
        revoked_at = dispatch.call_args.kwargs["kwargs"]["revoked_at"]
        assert revoked_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC).isoformat()

    def test_grant_and_revoke_dispatch_independently(self):
        with _seams() as (_, dispatch):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[_group(1)], removed=[_group(2)], actor=_ACTOR
            )
        assert dispatch.call_count == 2
        actions = [c.kwargs["kwargs"]["share_action"] for c in dispatch.call_args_list]
        assert actions == ["shared", "revoked"]

    def test_no_groups_skips_before_the_flag_check(self):
        with _seams() as (flag, dispatch):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[], removed=[], actor=_ACTOR
            )
        dispatch.assert_not_called()
        flag.assert_not_called()  # no Flipt call for a no-op share

    def test_flag_off_skips_dispatch(self):
        with _seams(enabled=False) as (_, dispatch):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[_group(1)], removed=[], actor=_ACTOR
            )
        dispatch.assert_not_called()

    def test_unknown_resource_kind_skips_dispatch(self):
        with (
            patch.object(sn, "kind_for_instance", return_value=None),
            patch.object(sn, "_feature_enabled", return_value=True),
            patch.object(sn, "_dispatch") as dispatch,
        ):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[_group(1)], removed=[], actor=_ACTOR
            )
        dispatch.assert_not_called()

    def test_missing_organization_skips_dispatch(self):
        orphan = SimpleNamespace(pk="wf-1", organization=None)
        with _seams() as (_, dispatch):
            sn.notify_resource_group_share_changed(
                resource=orphan, added=[_group(1)], removed=[], actor=_ACTOR
            )
        dispatch.assert_not_called()

    def test_dispatch_failure_never_reaches_the_caller(self):
        # The share has already committed — losing its email must not 500 it.
        with _seams(dispatch_raises=RuntimeError("queue down")):
            sn.notify_resource_group_share_changed(
                resource=_RESOURCE, added=[_group(1)], removed=[], actor=_ACTOR
            )


class TestNotifyGroupMembershipChanged:
    def test_membership_change_dispatches_user_ids_in_payload(self):
        with _seams() as (_, dispatch):
            sn.notify_group_membership_changed(
                group=SimpleNamespace(
                    pk=9, organization=SimpleNamespace(organization_id="org-a")
                ),
                action=sn.MembershipAction.ADDED,
                user_ids=[4, 1],
                actor=_ACTOR,
            )
        call = dispatch.call_args.kwargs
        assert call["task_name"] == sn.NOTIFY_MEMBERSHIP_CHANGED_TASK
        assert call["entity_id"] == "9"
        assert call["kwargs"] == {
            "group_id": 9,
            "actor_id": 7,
            "membership_action": "added",
            # Unlike a share, the ids ride in the payload: on removal the rows
            # are gone by delivery time.
            "user_ids": [1, 4],
            "organization_id": "org-a",
        }

    def test_no_users_skips_before_the_flag_check(self):
        with _seams() as (flag, dispatch):
            sn.notify_group_membership_changed(
                group=SimpleNamespace(
                    pk=9, organization=SimpleNamespace(organization_id="org-a")
                ),
                action=sn.MembershipAction.REMOVED,
                user_ids=[],
                actor=_ACTOR,
            )
        dispatch.assert_not_called()
        flag.assert_not_called()
