"""Tests for ``PromptStudioHelper.validate_profile_manager_owner_access``.

UN-3739: the check used to validate only the profile *creator*'s adapter
access — the requesting user was never passed in, so org admins were
denied on any project whose profile creator lost adapter access (share
revoked, member offboarded, or profile created by a service account via
the platform API).

Contract pinned here (evaluation order):

  1. Requester (a ``User`` object) is an org admin  → pass
  2. ``created_by`` is None                         → pass (unchanged)
  3. Creator is a service account                   → pass (platform-API)
  4. Creator is an org admin                        → pass (unchanged)
  5. Creator has access to all 4 adapters           → pass (delegated use)
  6. Otherwise → PermissionError blaming the creator role (never "You"),
     PII-free, as a plain string.

Unit tests: the real helper module is imported and collaborators are
patched per-test, so no database is touched.
"""

from __future__ import annotations

import inspect
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


def _adapter(name: str, owner: MagicMock) -> MagicMock:
    """Adapter mock for the UN-2202 access model: created_by is audit-only;
    access flows from owner/viewer membership roles, org share, or groups."""
    adapter = MagicMock(name=f"adapter-{name}")
    adapter.adapter_name = name
    adapter.shared_to_org = False
    adapter.owner_set = {owner}
    adapter.viewer_set = set()
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
    request_user: MagicMock | None = None,
    admin_users: tuple[MagicMock, ...] = (),
    group_access: bool = False,
    creator_is_member: bool = True,
) -> None:
    """Invoke the validator with OrganizationMemberService / group access patched.

    ``admin_users`` are Users for whom ``is_user_organization_admin``
    returns True.
    """
    oms = MagicMock(name="OrganizationMemberService")
    oms.is_user_organization_admin.side_effect = lambda u: u in admin_users
    oms.get_user_by_id.return_value = (
        MagicMock(name="creator-membership") if creator_is_member else None
    )

    with ExitStack() as stack:
        stack.enter_context(patch.object(_psh_mod, "OrganizationMemberService", oms))
        stack.enter_context(
            patch.object(
                _psh_mod,
                "_is_resource_owner",
                MagicMock(side_effect=lambda user, adapter: user in adapter.owner_set),
            )
        )
        stack.enter_context(
            patch.object(
                _psh_mod,
                "_is_resource_viewer",
                MagicMock(side_effect=lambda user, adapter: user in adapter.viewer_set),
            )
        )
        stack.enter_context(
            patch.object(
                _psh_mod, "has_group_access", MagicMock(return_value=group_access)
            )
        )
        PromptStudioHelper.validate_profile_manager_owner_access(
            profile, request_user=request_user
        )


class TestRequesterBypass:
    """Cases 1 and 7 of the UN-3739 matrix: the reported bug."""

    def test_admin_requester_passes_when_creator_lost_access(self) -> None:
        """Admin indexing a project whose creator lost adapter access → pass."""
        admin = _user("admin-1", "admin@org.com")
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)

        _run_check(profile, request_user=admin, admin_users=(admin,))

    def test_non_admin_requester_with_lapsed_creator_is_still_blocked(self) -> None:
        """Case 2: the revocation guard must survive the fix."""
        requester = _user("userc", "userc@org.com")
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)

        with pytest.raises(PSPermissionError):
            _run_check(profile, request_user=requester)

    def test_none_requester_falls_through_to_creator_checks(self) -> None:
        """Worker paths pass no requester — creator checks still decide."""
        creator = _user("userb", "userb@org.com")
        profile = _profile(creator, adapter_owner=creator)

        _run_check(profile, request_user=None)


class TestCreatorBypasses:
    def test_service_account_creator_passes(self) -> None:
        """Case 4: platform-API projects referencing others' adapters."""
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

        _run_check(profile, request_user=requester)


class TestCreatorAccessDisjuncts:
    """Each non-ownership access path must independently satisfy the guard.

    Review sabotage-check: reducing ``_adapter_accessible_by`` to its
    owner-role disjunct alone must fail these.
    """

    def _lapsed_profile(self) -> MagicMock:
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        return _profile(creator, adapter_owner=other)

    def test_org_shared_adapters_pass(self) -> None:
        profile = self._lapsed_profile()
        for attr in ("llm", "vector_store", "embedding_model", "x2text"):
            getattr(profile, attr).shared_to_org = True

        _run_check(profile)

    def test_viewer_shared_adapters_pass(self) -> None:
        profile = self._lapsed_profile()
        for attr in ("llm", "vector_store", "embedding_model", "x2text"):
            getattr(profile, attr).viewer_set.add(profile.created_by)

        _run_check(profile)

    def test_group_shared_adapters_pass(self) -> None:
        profile = self._lapsed_profile()

        _run_check(profile, group_access=True)


class TestDenialMessage:
    """The message must blame the creator role (never 'You'), carry no PII,
    and be a plain string.

    Post-fix the only audience for these denials is non-admin
    collaborators, so the creator's email stays in server logs only.
    """

    def _denied(self, *, creator_is_member: bool) -> PSPermissionError:
        creator = _user("userb", "userb@org.com")
        other = _user("userx", "userx@org.com")
        profile = _profile(creator, adapter_owner=other)
        # Creator has access to all but the LLM adapter — mirrors the
        # reported single-adapter denial.
        for attr in ("vector_store", "embedding_model", "x2text"):
            getattr(profile, attr).owner_set.add(creator)

        with pytest.raises(PSPermissionError) as exc_info:
            _run_check(profile, creator_is_member=creator_is_member)
        return exc_info.value

    def test_message_blames_creator_without_pii(self) -> None:
        exc = self._denied(creator_is_member=True)

        # A tuple detail (the old ``error_msg = (f"...",)`` bug) becomes a
        # list in DRF's APIException — detail must stay a plain string.
        assert isinstance(exc.detail, str), "error detail must be a string"
        message = str(exc)
        assert "userb@org.com" not in message, "no PII in user-facing errors"
        assert "created" in message
        assert "llm-1" in message
        assert "You do not have access" not in message
        assert "admin" in message, "remediation must point at an org admin"

    def test_message_flags_former_member_creator(self) -> None:
        """Case 7: offboarded creator — say so instead of a bare denial."""
        exc = self._denied(creator_is_member=False)
        message = str(exc)

        assert isinstance(exc.detail, str)
        assert "userb@org.com" not in message
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


class TestBuilderSignatures:
    """``request_user`` must be keyword-only with NO default on the four
    view-facing builders — a dropped plumb must fail loudly (TypeError),
    never silently revert to pre-fix behavior."""

    @pytest.mark.parametrize(
        "builder",
        [
            PromptStudioHelper.build_index_payload,
            PromptStudioHelper.build_fetch_response_payload,
            PromptStudioHelper.build_bulk_fetch_response_payload,
            PromptStudioHelper.build_single_pass_payload,
        ],
    )
    def test_request_user_is_required_keyword_only(self, builder) -> None:
        param = inspect.signature(builder).parameters["request_user"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty


class _Forwarded(Exception):
    """Sentinel raised by the patched validator to abort the builder."""


class TestBuilderForwarding:
    """Each builder must hand the requester object to the validator."""

    REQUEST_USER = MagicMock(name="request-user")

    @pytest.mark.parametrize(
        "builder_name, extra_kwargs_factory",
        [
            (
                "build_fetch_response_payload",
                lambda: {"prompt": MagicMock(name="prompt")},
            ),
            (
                "build_bulk_fetch_response_payload",
                lambda: {"prompts": [MagicMock(name="prompt")]},
            ),
            (
                "build_single_pass_payload",
                lambda: {"prompts": [MagicMock(name="prompt")]},
            ),
        ],
    )
    def test_builder_forwards_requester(self, builder_name, extra_kwargs_factory) -> None:
        validator = MagicMock(side_effect=_Forwarded())
        builder = getattr(PromptStudioHelper, builder_name)
        call_kwargs = {
            "tool": MagicMock(name="tool"),
            "doc_path": "/doc",
            "doc_name": "doc.pdf",
            "org_id": "org-1",
            "user_id": "owner-1",
            "document_id": "doc-1",
            "run_id": "run-1",
            "request_user": self.REQUEST_USER,
            **extra_kwargs_factory(),
        }
        with ExitStack() as stack:
            for target, attr, value in (
                (
                    _psh_mod.ProfileManager,
                    "get_default_llm_profile",
                    MagicMock(return_value=MagicMock(name="profile")),
                ),
                (
                    PromptStudioHelper,
                    "_resolve_llm_ids",
                    MagicMock(return_value=("m", "c")),
                ),
                (PromptStudioHelper, "validate_adapter_status", MagicMock()),
                (PromptStudioHelper, "validate_profile_manager_owner_access", validator),
            ):
                stack.enter_context(patch.object(target, attr, value))
            with pytest.raises(_Forwarded):
                builder(**call_kwargs)

        _args, kwargs = validator.call_args
        assert kwargs.get("request_user") is self.REQUEST_USER
