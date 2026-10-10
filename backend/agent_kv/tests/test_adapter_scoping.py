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
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.test import TestCase  # noqa: E402

from account_v2.models import Organization  # noqa: E402
from adapter_processor_v2.models import AdapterInstance  # noqa: E402
from rest_framework.exceptions import ValidationError  # noqa: E402

from agent_kv.execution_views import (  # noqa: E402
    _lookup_adapter,
    _resolved_adapters,
)
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


class TestResolvedAdaptersAgainstRealRows(TestCase):
    """`_resolved_adapters` end-to-end against the database, not against mocks.

    `test_submit_view.py` patches `ev._lookup_adapter`, so every property the
    gate reads off an adapter -- `adapter_type`, `is_usable`, `is_available` --
    is only ever compared to a value the stand-in chose for itself. That is
    enough to test the gate's branching and nothing about whether the branches
    match the real columns. These rows get their flags from the model's own
    defaults.

    It is also the only place the refusal-oracle property can honestly be
    tested: "not yours" and "no such adapter" have to come from two GENUINELY
    different database states, which a single mocked lookup cannot produce.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        self.other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        self.key = mock.Mock(organization_id=self.org.id)
        UserContext.set_organization_identifier(None)

    def _adapter(self, *, org=None, adapter_type="LLM", **kwargs):
        return AdapterInstance.objects.create(
            adapter_name=f"a-{uuid.uuid4().hex[:8]}",
            adapter_id="anthropic|abc",
            adapter_type=adapter_type,
            adapter_metadata={},
            organization=org or self.org,
            **kwargs,
        )

    def _entry(self, **roles):
        return {"name": "table", "adapters": {r: str(v) for r, v in roles.items()}}

    def _full_entry(self, **overrides):
        roles = {
            "llm": self._adapter().id,
            "lite_llm": self._adapter().id,
            "x2text": self._adapter(adapter_type="X2TEXT").id,
        }
        roles.update(overrides)
        return self._entry(**roles)

    def test_a_fully_valid_set_of_the_org_s_own_adapters_resolves(self):
        """The happy path, with every flag coming from the DB's own defaults.

        `is_usable` and `is_available` both default True at the model, so this
        also pins that the two new refusals do not reject ordinary adapters
        nobody has touched.
        """
        entry = self._full_entry()

        self.assertEqual(_resolved_adapters(entry, self.key), entry["adapters"])

    def test_a_wrong_type_is_refused_against_a_real_row(self):
        """An X2TEXT id in the `llm` slot.

        Previously asserted only against a mock that was told to report
        `adapter_type="X2TEXT"`; this reads the real column, so the comparison
        against `AdapterTypes.LLM.value` is pinned to the value the DB stores.
        """
        entry = self._full_entry(llm=self._adapter(adapter_type="X2TEXT").id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("expected 'LLM'", str(caught.exception))

    def test_an_exhausted_trial_adapter_is_refused(self):
        """A1. `is_usable=False` is how billing cuts off a frictionless trial.

        The platform service returns the credentials regardless, so this gate
        is the only thing that stops an operator-funded extraction here.
        """
        entry = self._full_entry(llm=self._adapter(is_usable=False).id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("exhausted", str(caught.exception))

    def test_a_deprecated_adapter_is_refused(self):
        entry = self._full_entry(llm=self._adapter(is_available=False).id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("deprecated", str(caught.exception))

    def test_another_org_s_adapter_and_a_nonexistent_one_refuse_identically(self):
        """The oracle property, from two genuinely different DB states.

        If these two messages ever diverge, `POST /agent-kv/` becomes an oracle
        for which adapter UUIDs are real in OTHER organizations: a caller
        brute-forcing ids learns "exists but not yours" from "does not exist".

        The mocked version of this test could not fail -- one patched lookup
        returns None for both cases, so it compared one branch's message to
        itself. Here one id is a real row owned by `self.other` and the other
        is a UUID no row has.
        """
        foreign = self._adapter(org=self.other).id
        nowhere = uuid.uuid4()

        messages = []
        for adapter_id in (foreign, nowhere):
            with self.assertRaises(ValidationError) as caught:
                _resolved_adapters(self._full_entry(llm=adapter_id), self.key)
            messages.append(str(caught.exception))

        self.assertEqual(
            messages[0],
            messages[1],
            "a foreign adapter and a nonexistent one must be indistinguishable; "
            f"got {messages[0]!r} vs {messages[1]!r}",
        )

    def test_no_adapters_requested_is_a_no_op(self):
        """The `kv` shape: env-configured extractors send `{}` and must pass."""
        self.assertEqual(_resolved_adapters({"name": "kv", "adapters": {}}, self.key), {})


class TestTheJobRowRecordsWhatItSpent(TestCase):
    """The adapters a run was dispatched with must be recoverable AFTERWARDS.

    Adapter choice is per-request, caller-controlled and cost-bearing on the
    `table` path. Before the `adapters` column the chosen ids reached
    `executor_params` and nothing else -- not the job row, not the status
    document, not `usage_summary` -- so "which model did job X use?", the first
    question in any billing dispute, needed a `usage_v2` join on `run_id` that
    the API cannot perform and the customer cannot see.

    DB-backed because the point is that the value SURVIVES the request.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        from agent_kv.models import AgentKVJob, JobExtractor

        job = AgentKVJob(
            organization_id=self.org.id,
            extractor=JobExtractor.TABLE,
            **kwargs,
        )
        job.save()
        return job

    def test_the_adapters_round_trip_through_the_database(self):
        adapters = {
            "llm": str(uuid.uuid4()),
            "lite_llm": str(uuid.uuid4()),
            "x2text": str(uuid.uuid4()),
        }

        job = self._job(adapters=adapters)
        job.refresh_from_db()

        assert job.adapters == adapters

    def test_the_status_document_reports_them(self):
        from agent_kv.execution_views import _status_document

        adapters = {"llm": str(uuid.uuid4())}
        doc = _status_document(self._job(adapters=adapters))

        assert doc["adapters"] == adapters, doc

    def test_a_job_with_no_adapters_reports_an_empty_dict_not_null(self):
        """`kv` is env-configured and names none, and rows predating the column
        genuinely ran on operator credentials -- `{}` is the honest value for
        both, and a stable type is easier for a client than `null | object`.
        """
        from agent_kv.execution_views import _status_document

        job = self._job()

        assert job.adapters == {}
        assert _status_document(job)["adapters"] == {}

    def test_no_adapter_metadata_is_ever_stored_on_the_job(self):
        """The column is returned to the caller, so it must carry ids only.

        `AdapterInstance.adapter_metadata` holds the PROVIDER CREDENTIALS. A
        future change that widened this field to "the adapter" rather than "its
        id" would publish those to whoever submitted the job.
        """
        adapters = {"llm": str(uuid.uuid4()), "x2text": str(uuid.uuid4())}
        job = self._job(adapters=adapters)
        job.refresh_from_db()

        for role, value in job.adapters.items():
            assert isinstance(value, str), (role, value)
            # A bare UUID string, not a serialized adapter.
            uuid.UUID(value)
