"""Unit tests for user-identity resolution in ``AuthenticationHelper``.

These are no-database ``SimpleTestCase`` tests: ``UserService`` is mocked so
only the resolution/branching logic of ``get_or_create_user_by_email`` is
exercised. They guard against the duplicate-account regression where a person
with more than one Auth0 connection (e.g. SAML + passwordless email) on the
same email ended up with two ``User`` rows (see UN-3525).
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from account_v2.authentication_helper import AuthenticationHelper


class GetOrCreateUserByEmailTests(SimpleTestCase):
    @patch("account_v2.authentication_helper.UserService")
    def test_resolves_by_user_id_first(self, mock_user_service: MagicMock) -> None:
        """An existing row matching the Auth0 ``user_id`` is reused as-is, even
        though it may have been created by a different login path.
        """
        svc = mock_user_service.return_value
        existing = MagicMock(name="existing_user")
        svc.get_user_by_user_id.return_value = existing

        result = AuthenticationHelper.get_or_create_user_by_email(
            user_id="samlp|mars|user@example.com", email="user@example.com"
        )

        self.assertIs(result, existing)
        svc.get_user_by_user_id.assert_called_once_with("samlp|mars|user@example.com")
        # Must not fall through to email lookup / create when user_id matched.
        svc.get_user_by_email.assert_not_called()
        svc.update_user.assert_not_called()
        svc.create_user.assert_not_called()

    @patch("account_v2.authentication_helper.UserService")
    def test_backfills_user_id_on_email_match_without_user_id(
        self, mock_user_service: MagicMock
    ) -> None:
        """A pre-provisioned (invited) row with no ``user_id`` gets the
        ``user_id`` backfilled instead of creating a new row.
        """
        svc = mock_user_service.return_value
        svc.get_user_by_user_id.return_value = None
        invited = MagicMock(user_id="")
        svc.get_user_by_email.return_value = invited
        updated = MagicMock(name="updated_user")
        svc.update_user.return_value = updated

        result = AuthenticationHelper.get_or_create_user_by_email(
            user_id="auth0|abc", email="user@example.com"
        )

        svc.update_user.assert_called_once_with(invited, "auth0|abc")
        self.assertIs(result, updated)
        svc.create_user.assert_not_called()

    @patch("account_v2.authentication_helper.UserService")
    def test_reuses_email_match_with_existing_user_id(
        self, mock_user_service: MagicMock
    ) -> None:
        """An email match that already has a ``user_id`` is reused without
        overwriting its ``user_id`` and without creating a new row.
        """
        svc = mock_user_service.return_value
        svc.get_user_by_user_id.return_value = None
        existing = MagicMock()
        existing.user_id = "auth0|other"
        svc.get_user_by_email.return_value = existing

        result = AuthenticationHelper.get_or_create_user_by_email(
            user_id="auth0|abc", email="user@example.com"
        )

        self.assertIs(result, existing)
        svc.update_user.assert_not_called()
        svc.create_user.assert_not_called()

    @patch("account_v2.authentication_helper.UserService")
    def test_creates_user_when_no_match(self, mock_user_service: MagicMock) -> None:
        """A brand-new identity (no user_id and no email match) is created."""
        svc = mock_user_service.return_value
        svc.get_user_by_user_id.return_value = None
        svc.get_user_by_email.return_value = None
        created = MagicMock(name="created_user")
        svc.create_user.return_value = created

        result = AuthenticationHelper.get_or_create_user_by_email(
            user_id="auth0|abc", email="user@example.com"
        )

        svc.create_user.assert_called_once_with("user@example.com", "auth0|abc")
        self.assertIs(result, created)
