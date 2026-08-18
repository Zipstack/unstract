"""Regression tests for UserContext.get_organization.

Pins the no-org short-circuit: the lookup must return None without touching the
DB, so it stays evaluable on a DB-less/unmigrated setup.
"""

from __future__ import annotations

from unittest.mock import patch

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
