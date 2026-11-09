"""Shared fixtures: one org with an admin and a member, a second org, and a
helper that calls a view the way a request would and runs its on-commit writes.
"""

import secrets
from typing import Any

from account_v2.models import Organization, User
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.tests.auth_seam import admin_role, member_role
from utils.user_context import UserContext

from platform_audit.models import PlatformAuditEvent


def make_user(email: str, **kwargs: Any) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe(), **kwargs
    )


class AuditTestBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        self.use_org(self.org)
        self.admin_role, self.member_role = admin_role(), member_role()
        self.admin = make_user("Admin@Example.com", first_name="Ada", last_name="Min")
        self.member = make_user("member@example.com")
        OrganizationMember.objects.create(
            organization=self.org, user=self.admin, role=self.admin_role
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.member, role=self.member_role
        )
        self.factory = APIRequestFactory()

    def use_org(self, organization: Organization) -> None:
        UserContext.set_organization_identifier(organization.organization_id)

    def call(
        self,
        view: Any,
        method: str,
        user: User | None = None,
        data: Any = None,
        path: str = "/",
        platform_api_key: Any = None,
        **url_kwargs: Any,
    ) -> Any:
        """Run ``view`` and every on-commit callback it registers."""
        request = getattr(self.factory, method)(path, data, format="json")
        request.id = "req-123"
        request.session = {"organization": self.org.organization_id}
        if platform_api_key is not None:
            request.platform_api_key = platform_api_key
        force_authenticate(request, user=user or self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = view(request, **url_kwargs)
        return response

    def events(self, **filters: Any) -> list[PlatformAuditEvent]:
        return list(
            PlatformAuditEvent.objects.filter(**filters).order_by("occurred_at", "id")
        )

    def only_event(self, **filters: Any) -> PlatformAuditEvent:
        events = self.events(**filters)
        self.assertEqual(len(events), 1, [e.action for e in events])
        return events[0]

    def assert_admin_actor(self, event: PlatformAuditEvent) -> None:
        self.assertEqual(event.organization, self.org)
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_email, "admin@example.com")
        self.assertEqual(event.actor_name, "Ada Min")
        self.assertEqual(event.request_id, "req-123")
