"""The seam helpers answer from the active auth service, and say when they cannot."""

from django.test import SimpleTestCase

from utils.tests.auth_seam import (
    active_auth_service,
    admin_role,
    member_role,
    patch_auth_service,
)


class RoleNameTests(SimpleTestCase):
    def test_roles_match_the_active_service(self) -> None:
        service = active_auth_service()
        self.assertTrue(service.is_admin_by_role(admin_role()))
        self.assertFalse(service.is_admin_by_role(member_role()))

    def test_unknown_role_vocabulary_fails_loudly(self) -> None:
        with patch_auth_service("is_admin_by_role", return_value=False):
            with self.assertRaisesRegex(AssertionError, "teach utils.tests.auth_seam"):
                admin_role()
