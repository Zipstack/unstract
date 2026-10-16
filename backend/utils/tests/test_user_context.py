"""Regression tests for UserContext.get_organization.

Pins the no-org short-circuit: the lookup must return None without touching the
DB, so it stays evaluable on a DB-less/unmigrated setup. Also pins the
per-request organization cache (UN-4253).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from account_v2.models import Organization
from django.db.utils import ProgrammingError

from utils.constants import Account
from utils.local_context import StateStore
from utils.user_context import UserContext


class TestGetOrganizationNoContext:
    def test_returns_none_without_hitting_db(self):
        with (
            patch("utils.user_context.StateStore.get", return_value=None),
            patch("utils.user_context.Organization.objects.get") as mock_get,
        ):
            assert UserContext.get_organization() is None
            mock_get.assert_not_called()

    def test_empty_identifier_short_circuits(self):
        with (
            patch("utils.user_context.StateStore.get", return_value=""),
            patch("utils.user_context.Organization.objects.get") as mock_get,
        ):
            assert UserContext.get_organization() is None
            mock_get.assert_not_called()

    def test_identifier_present_looks_up_organization(self):
        """Pins the complement, so inverting the guard can't pass unnoticed."""
        sentinel = object()
        with (
            patch("utils.user_context.StateStore.get", return_value="org-123"),
            patch(
                "utils.user_context.Organization.objects.get", return_value=sentinel
            ) as mock_get,
        ):
            assert UserContext.get_organization() is sentinel
            mock_get.assert_called_once_with(organization_id="org-123")


# --- Per-request organization cache (UN-4253) --------------------------------
#
# These run against the real StateStore: what is under test is how the cache
# reacts to the organization id being set and cleared, which a patched
# StateStore would hide.

_LOOKUP = "utils.user_context.Organization.objects.get"


def _reset_state() -> None:
    for key in (Account.ORGANIZATION_ID, Account.ORGANIZATION_CACHE):
        if hasattr(StateStore.thread_local, key):
            delattr(StateStore.thread_local, key)


@pytest.fixture(autouse=True)
def clean_state_store():
    _reset_state()
    yield
    _reset_state()


class _Org:
    """Stands in for an Organization row; only identity and pk are read."""

    def __init__(self, organization_id: str, pk: int | None = 1):
        self.organization_id = organization_id
        self.pk = pk


def _lookup_returning(*orgs: _Org):
    by_id = {org.organization_id: org for org in orgs}
    return patch(_LOOKUP, side_effect=lambda organization_id: by_id[organization_id])


class TestOrganizationCache:
    def test_resolved_once_per_request(self):
        org = _Org("org-a")
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        with _lookup_returning(org) as lookup:
            for _ in range(5):
                assert UserContext.get_organization() is org
        lookup.assert_called_once_with(organization_id="org-a")

    def test_switching_org_never_returns_the_previous_one(self):
        """Tenant boundary: a cached org is only valid for the id it was built for."""
        org_a, org_b = _Org("org-a", pk=1), _Org("org-b", pk=2)
        with _lookup_returning(org_a, org_b):
            StateStore.set(Account.ORGANIZATION_ID, "org-a")
            assert UserContext.get_organization() is org_a
            StateStore.set(Account.ORGANIZATION_ID, "org-b")
            assert UserContext.get_organization() is org_b

    def test_cache_entry_for_another_id_is_ignored(self):
        """Even if an entry survived an id change, it must not be served."""
        org_a, org_b = _Org("org-a", pk=1), _Org("org-b", pk=2)
        StateStore.set(Account.ORGANIZATION_ID, "org-b")
        StateStore.set(Account.ORGANIZATION_CACHE, ("org-a", org_a))
        with _lookup_returning(org_b) as lookup:
            assert UserContext.get_organization() is org_b
        lookup.assert_called_once_with(organization_id="org-b")

    def test_setting_the_same_id_again_resolves_afresh(self):
        """Each request starts by setting the id, so settings changed by an
        admin between requests (e.g. restrict_connector_creation) are seen.
        """
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        with _lookup_returning(_Org("org-a")) as lookup:
            UserContext.get_organization()
            StateStore.set(Account.ORGANIZATION_ID, "org-a")
            UserContext.get_organization()
        assert lookup.call_count == 2

    def test_clearing_the_id_drops_the_cache(self):
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        with _lookup_returning(_Org("org-a")):
            UserContext.get_organization()
        StateStore.clear(Account.ORGANIZATION_ID)
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None

    def test_clear_of_an_unset_id_still_raises(self):
        """Callers rely on this (they suppress AttributeError)."""
        with pytest.raises(AttributeError):
            StateStore.clear(Account.ORGANIZATION_ID)

    def test_not_found_is_not_cached(self):
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        with patch(_LOOKUP, side_effect=Organization.DoesNotExist) as lookup:
            assert UserContext.get_organization() is None
            assert UserContext.get_organization() is None
        assert lookup.call_count == 2
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None

    def test_programming_error_is_not_cached(self):
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        with patch(_LOOKUP, side_effect=ProgrammingError) as lookup:
            assert UserContext.get_organization() is None
            assert UserContext.get_organization() is None
        assert lookup.call_count == 2

    def test_deleted_instance_is_not_served(self):
        """Django sets pk to None on delete; fall back to the lookup."""
        deleted = _Org("org-a", pk=None)
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        StateStore.set(Account.ORGANIZATION_CACHE, ("org-a", deleted))
        fresh = _Org("org-a", pk=7)
        with _lookup_returning(fresh):
            assert UserContext.get_organization() is fresh


class TestCacheOrganization:
    def test_seeded_org_is_served_without_a_lookup(self):
        org = _Org("org-a")
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        UserContext.cache_organization(org)
        with patch(_LOOKUP) as lookup:
            assert UserContext.get_organization() is org
        lookup.assert_not_called()

    def test_seeding_another_org_is_ignored(self):
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        UserContext.cache_organization(_Org("org-b"))
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None

    def test_seeding_without_an_id_is_ignored(self):
        UserContext.cache_organization(_Org("org-a"))
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None

    def test_clear_organization_cache(self):
        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        UserContext.cache_organization(_Org("org-a"))
        UserContext.clear_organization_cache()
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None
        UserContext.clear_organization_cache()  # idempotent

    def test_celery_task_postrun_drops_the_cache(self):
        from backend.celery_service import _drop_cached_organization

        StateStore.set(Account.ORGANIZATION_ID, "org-a")
        UserContext.cache_organization(_Org("org-a"))
        _drop_cached_organization(task_id="t", task=None)
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None
