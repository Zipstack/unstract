"""The adapter lookup must work with NO request-local organization context.

This is the test whose absence let a P1 through. `_resolved_adapters` was
written with `AdapterInstance.objects`, by analogy to the `organization_id`
filter in `_get_job` -- but the two models have different default managers:

* `AgentKVJob` uses `BaseModelManager`, which does not auto-filter, so its
  explicit `organization_id=` is the only filter.
* `AdapterInstance` sets `AdapterInstanceModelManager`, which inherits
  `DefaultOrganizationManagerMixin.get_queryset()` and filters EVERY query by
  `UserContext.get_organization()` -- a request-local thread-local set by the
  tenant middleware.

`/agent-kv/` is deliberately whitelisted past that middleware (the org comes
from the Bearer key, not the URL), so the thread-local is unset and the ambient
filter became `organization=None`. Every valid submit was refused with "no such
adapter in this organization".

Every test in `test_submit_view.py` mocked the lookup, so none of them could
see it. These run against the real manager with the real thread-local unset --
which is the only arrangement that reproduces the production path.

DB-backed, so `TestCase` and the integration tier (`backend/conftest.py`
auto-marks on that basis; no manual marker).
"""

import os
import uuid

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.test import TestCase  # noqa: E402

from account_v2.models import Organization  # noqa: E402
from adapter_processor_v2.models import AdapterInstance  # noqa: E402
from agent_kv.execution_views import _lookup_adapter  # noqa: E402
from utils.user_context import UserContext  # noqa: E402


class TestAdapterLookupWithoutRequestContext(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        self.other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        self.adapter = AdapterInstance.objects.create(
            adapter_name="acme-llm",
            adapter_id="anthropic|abc",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
        )
        # The state the whitelisted route actually runs in: no tenant
        # middleware has run, so there is no ambient organization.
        UserContext.set_organization_identifier(None)

    def test_the_lookup_finds_the_org_s_own_adapter_with_no_user_context(self):
        """The regression. Through `.objects` this returned None and the submit
        was a 400 -- for a correctly-configured caller naming their own adapter.
        """
        self.assertIsNone(
            UserContext.get_organization(),
            "precondition: this route has no ambient organization",
        )

        found = _lookup_adapter(self.adapter.id, self.org.id)

        self.assertIsNotNone(
            found,
            "the caller's own adapter must resolve without a request-local "
            "organization; `.objects` filters by one and returns nothing here",
        )
        self.assertEqual(found.id, self.adapter.id)
        self.assertEqual(found.adapter_type, "LLM")

    def test_the_org_filter_still_excludes_another_org_s_adapter(self):
        """Bypassing the AMBIENT filter must not bypass the explicit one.

        `_base_manager` is unfiltered, so the `organization_id` argument is the
        only tenant boundary left -- if it stopped working, the fix for the
        regression above would have opened the cross-tenant hole it exists to
        close.
        """
        self.assertIsNone(_lookup_adapter(self.adapter.id, self.other.id))

    def test_an_unknown_id_resolves_to_none(self):
        self.assertIsNone(_lookup_adapter(uuid.uuid4(), self.org.id))

    def test_the_ambient_manager_really_does_hide_it(self):
        """Pins the cause, so the comment on `_lookup_adapter` stays truthful.

        If `AdapterInstance.objects` ever stops auto-filtering by the
        thread-local, this fails and `_base_manager` is no longer necessary --
        at which point the explanation should be revisited rather than left
        asserting something that is no longer true.
        """
        via_objects = AdapterInstance.objects.filter(
            id=self.adapter.id, organization_id=self.org.id
        ).first()

        self.assertIsNone(
            via_objects,
            "`.objects` is expected to hide the adapter here -- that is the "
            "whole reason `_lookup_adapter` uses `_base_manager`",
        )
