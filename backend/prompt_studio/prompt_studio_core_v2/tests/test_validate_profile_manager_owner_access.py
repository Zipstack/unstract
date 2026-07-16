"""Tests for ``PromptStudioHelper.validate_profile_manager_owner_access``.

UN-3739: the check used to validate only the profile *creator*'s adapter
access — the requesting user was never passed in, so org admins were
denied on any project whose profile creator lost adapter access (share
revoked, member offboarded, or profile created by a service account via
the platform API).

Contract pinned here (evaluation order):

  1. Requester is an org admin              → pass (implicit access)
  2. ``created_by`` is None                 → pass (unchanged)
  3. Creator is a service account           → pass (platform-API projects)
  4. Creator is an org admin                → pass (unchanged)
  5. Creator has access to all 4 adapters   → pass (delegated use kept)
  6. Otherwise                              → PermissionError naming the
     CREATOR (not "You"), with remediation, as a plain string.

Unit tests: the real helper module is imported and collaborators are
patched per-test, so no database is touched.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from prompt_studio.prompt_studio_core_v2 import prompt_studio_helper as _psh_mod
from prompt_studio.prompt_studio_core_v2.exceptions import (
    PermissionError as PSPermissionError,
)

PromptStudioHelper = _psh_mod.PromptStudioHelper


def _user(user_id: str, email: str, *, service_account: bool = False) -> MagicMock:
    user = MagicMock(name=f"user-{user_id}")
    user.id = f"pk-{user_id}"
    user.user_id = user_id
    user.email = email
    user.is_service_account = service_account
    return user


def _adapter(name: str, created_by: MagicMock) -> MagicMock:
    adapter = MagicMock(name=f"adapter-{name}")
    adapter.adapter_name = name
    adapter.created_by = created_by
    adapter.shared_to_org = False
    adapter.shared_users.filter.return_value.exists.return_value = False
    return adapter


def _profile(creator: MagicMock | None, adapter_owner: MagicMock) -> MagicMock:
    """Profile whose 4 adapters are all owned by ``adapter_owner``."""
    profile = MagicMock(name="ProfileManager")
    profile.profile_name = "Default"
    profile.created_by = creator
    profile.llm = _adapter("llm-1", adapter_owner)
    profile.vector_store = _adapter("vdb-1", adapter_owner)
    profile.embedding_model = _adapter("emb-1", adapter_owner)
    profile.x2text = _adapter("x2t-1", adapter_owner)
    return profile


def _run_check(
    profile: MagicMock,
    *,
    request_user_id: str | None = None,
    admin_users: tuple[MagicMock, ...] = (),
    members_by_user_id: dict[str, MagicMock] | None = None,
    creator_is_member: bool = True,
) -> None:
    """Invoke the validator with OrganizationMemberService / group access patched.

    ``members_by_user_id`` maps a request_user_id to an OrganizationMember
    mock (``.user`` set); missing ids resolve to None.  ``admin_users``
    are Users for whom ``is_user_organization_admin`` returns True.
    """
    members_by_user_id = members_by_user_id or {}

    oms = MagicMock(name="OrganizationMemberService")
    oms.is_user_organization_admin.side_effect = lambda u: u in admin_users
    oms.get_user_by_user_id.side_effect = lambda uid: members_by_user_id.get(uid)
    oms.get_user_by_id.return_value = (
        MagicMock(name="creator-membership") if creator_is_member else None
    )

    with ExitStack() as stack:
        stack.enter_context(patch.object(_psh_mod, "OrganizationMemberService", oms))
        stack.enter_context(
            patch.object(_psh_mod, "has_group_access", MagicMock(return_value=False))
        )
        PromptStudioHelper.validate_profile_manager_owner_access(
            profile, request_user_id=request_user_id
        )


def _member_for(user: MagicMock) -> MagicMock:
    member = MagicMock(name=f"member-{user.user_id}")
    member.user = user
    return member


class TestRequesterBypass:
    """Cases 1 and 7 of the UN-3739 matrix: the reported bug."""

    def test_admin_requester_passes_when_creator_lost_access(self) -> None:
        """Admin indexing a project whose creator lost adapter access → pass."""
        admin = _user("admin-1", "admin@org.com")
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)

        _run_check(
            profile,
            request_user_id="admin-1",
            admin_users=(admin,),
            members_by_user_id={"admin-1": _member_for(admin)},
        )

    def test_non_admin_requester_with_lapsed_creator_is_still_blocked(self) -> None:
        """Case 2: the revocation guard must survive the fix."""
        requester = _user("userc", "userc@org.com")
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)

        with pytest.raises(PSPermissionError):
            _run_check(
                profile,
                request_user_id="userc",
                members_by_user_id={"userc": _member_for(requester)},
            )

    def test_unknown_request_user_id_falls_through_to_creator_checks(self) -> None:
        """A user_id with no membership row must not crash the check."""
        creator = _user("userb", "userb@org.com")
        profile = _profile(creator, adapter_owner=creator)

        _run_check(profile, request_user_id="ghost-user")


class TestCreatorBypasses:
    def test_service_account_creator_passes(self) -> None:
        """Case 4: platform-API / org-migration projects (the customer's setup)."""
        sa_creator = _user("sa-1", "sa@org.com", service_account=True)
        other = _user("userx", "userx@org.com")
        profile = _profile(sa_creator, adapter_owner=other)

        _run_check(profile)

    def test_admin_creator_passes(self) -> None:
        """Case 3: existing behavior kept — creator-admin bypass."""
        admin_creator = _user("admin-1", "admin@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(admin_creator, adapter_owner=other)

        _run_check(profile, admin_users=(admin_creator,))

    def test_none_creator_passes(self) -> None:
        """Case 8: SET_NULL creator skips the check (unchanged)."""
        other = _user("userx", "userx@org.com")
        profile = _profile(None, adapter_owner=other)

        _run_check(profile)

    def test_creator_with_access_passes_for_any_requester(self) -> None:
        """Cases 5/6: delegated use — creator owns the adapters."""
        creator = _user("userb", "userb@org.com")
        requester = _user("userc", "userc@org.com")
        profile = _profile(creator, adapter_owner=creator)

        _run_check(
            profile,
            request_user_id="userc",
            members_by_user_id={"userc": _member_for(requester)},
        )


class TestDenialMessage:
    """The message must name the creator, not 'You', and be a plain string."""

    def _denied(self, *, creator_is_member: bool) -> PSPermissionError:
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)
        # Creator has access to all but the LLM adapter — mirrors the
        # customer's single-adapter denial.
        for attr in ("vector_store", "embedding_model", "x2text"):
            getattr(profile, attr).created_by = creator

        with pytest.raises(PSPermissionError) as exc_info:
            _run_check(profile, creator_is_member=creator_is_member)
        return exc_info.value

    def test_message_names_creator_and_adapter(self) -> None:
        exc = self._denied(creator_is_member=True)

        # A tuple detail (the old ``error_msg = (f"...",)`` bug) becomes a
        # list in DRF's APIException — detail must stay a plain string.
        assert isinstance(exc.detail, str), "error detail must be a string"
        message = str(exc)
        assert "userb@org.com" in message
        assert "llm-1" in message
        assert "You do not have access" not in message

    def test_message_flags_former_member_creator(self) -> None:
        """Case 7: offboarded creator — say so instead of a bare denial."""
        exc = self._denied(creator_is_member=False)
        message = str(exc)

        assert isinstance(exc.detail, str)
        assert "userb@org.com" in message
        assert "no longer a member" in message

    def test_message_lists_all_inaccessible_adapters(self) -> None:
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)

        with pytest.raises(PSPermissionError) as exc_info:
            _run_check(profile)
        message = str(exc_info.value)

        assert isinstance(exc_info.value.detail, str)
        for adapter_name in ("llm-1", "vdb-1", "emb-1", "x2t-1"):
            assert adapter_name in message
