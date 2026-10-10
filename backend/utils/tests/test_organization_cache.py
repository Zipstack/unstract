"""Org-scoped querysets resolve the request's organization once (UN-4253).

``DefaultOrganizationManagerMixin`` asks ``UserContext.get_organization()``
for the organization on every queryset. Without the per-request cache each of
those cost an extra ``SELECT ... FROM organization``, about one in six of the
statements the database ran under load. These pin the saving and that it
does not weaken the tenant boundary or serve stale settings.
"""

import secrets

import pytest
from account_v2.models import Organization
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from utils.constants import Account
from utils.local_context import StateStore
from utils.user_context import UserContext


def _organization_lookups(queries) -> int:
    return sum(1 for q in queries if 'FROM "organization"' in q["sql"])


@pytest.mark.django_db
class OrganizationCacheTest(TestCase):
    def setUp(self) -> None:
        self.org_a = self._org("a")
        self.org_b = self._org("b")
        self.wf_a = Workflow._base_manager.create(
            workflow_name=f"wf-a-{secrets.token_hex(3)}", organization=self.org_a
        )
        self.wf_b = Workflow._base_manager.create(
            workflow_name=f"wf-b-{secrets.token_hex(3)}", organization=self.org_b
        )

    def tearDown(self) -> None:
        for key in (Account.ORGANIZATION_ID, Account.ORGANIZATION_CACHE):
            if hasattr(StateStore.thread_local, key):
                delattr(StateStore.thread_local, key)

    def _org(self, tag: str) -> Organization:
        slug = f"org-{tag}-{secrets.token_hex(3)}"
        return Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )

    def test_org_resolved_once_across_querysets(self):
        StateStore.set(Account.ORGANIZATION_ID, self.org_a.organization_id)
        with CaptureQueriesContext(connection) as ctx:
            for _ in range(5):
                assert list(Workflow.objects.all()) == [self.wf_a]
        assert _organization_lookups(ctx.captured_queries) == 1

    def test_switching_org_scopes_to_the_new_org(self):
        StateStore.set(Account.ORGANIZATION_ID, self.org_a.organization_id)
        assert list(Workflow.objects.all()) == [self.wf_a]
        StateStore.set(Account.ORGANIZATION_ID, self.org_b.organization_id)
        assert list(Workflow.objects.all()) == [self.wf_b]

    def test_next_request_sees_changed_settings(self):
        """An admin toggling a controlled-mode flag must take effect on the
        next request, even on a thread that served the org before.
        """
        StateStore.set(Account.ORGANIZATION_ID, self.org_a.organization_id)
        assert UserContext.get_organization().restrict_connector_creation is False
        Organization.objects.filter(pk=self.org_a.pk).update(
            restrict_connector_creation=True
        )
        # A new request on the same thread starts by setting the id.
        StateStore.set(Account.ORGANIZATION_ID, self.org_a.organization_id)
        assert UserContext.get_organization().restrict_connector_creation is True

    def test_seeded_org_needs_no_lookup(self):
        StateStore.set(Account.ORGANIZATION_ID, self.org_a.organization_id)
        UserContext.cache_organization(self.org_a)
        with CaptureQueriesContext(connection) as ctx:
            assert list(Workflow.objects.all()) == [self.wf_a]
        assert _organization_lookups(ctx.captured_queries) == 0
